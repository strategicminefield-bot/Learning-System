#!/usr/bin/env python3
"""
OpenClaw Executor Adapter for Learning Fabric

Connects this OpenClaw instance to the Learning Fabric as a real executor node.
Enables real work assignment and execution through the Fabric.
Supports budget controls via --budget-config.

Configuration: ~/.openclaw/executor_config.json (persists node identity)
"""

import json
import os
import uuid
import requests
import time
import sys
import subprocess
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Budget control module
from fabric.budget.budget_controller import (
    BudgetConfig, BudgetController, BudgetStateStore,
    BudgetState, BudgetExceeded, DeadlineWatchdog,
    DEFAULT_BUDGET_DIR
)

# Configuration
CONFIG_DIR = Path.home() / ".openclaw"
CONFIG_FILE = CONFIG_DIR / "executor_config.json"
DEFAULT_FABRIC_URL = "http://95.179.236.41:8000"
HEARTBEAT_INTERVAL = 30
POLL_INTERVAL = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class ExecutorConfig:
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        if self.config_file.exists():
            with open(self.config_file) as f:
                return json.load(f)
        config = {
            "node_id": str(uuid.uuid4()),
            "node_type": "executor",
            "provider": "openclaw",
            "display_name": "OpenClaw Executor (WSL)",
            "fabric_url": DEFAULT_FABRIC_URL,
            "heartbeat_interval": HEARTBEAT_INTERVAL,
            "poll_interval": POLL_INTERVAL,
            "capabilities": ["code_execution", "task_automation", "analysis", "text_generation"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self._save(config)
        return config

    def _save(self, config):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)

    @property
    def node_id(self) -> str:
        return self.config["node_id"]

    @property
    def fabric_url(self) -> str:
        return self.config.get("fabric_url", DEFAULT_FABRIC_URL)


class FabricClient:
    def __init__(self, fabric_url: str, node_id: str):
        self.fabric_url = fabric_url
        self.node_id = node_id
        self.root_url = fabric_url
        self.session = requests.Session()

    def check_node_registered(self) -> bool:
        try:
            resp = self.session.get(f"{self.root_url}/workers", timeout=10)
            if resp.status_code == 200:
                workers = resp.json()
                if isinstance(workers, list):
                    for w in workers:
                        nid = w.get("node_id") if isinstance(w, dict) else w
                        if nid == self.node_id:
                            logger.info(f"Node {self.node_id[:12]}... confirmed registered")
                            return True
                return False
            return False
        except Exception as e:
            logger.warning(f"Registration check error: {e}")
            return False

    def send_heartbeat(self, status: str = "available") -> bool:
        try:
            resp = self.session.post(
                f"{self.root_url}/workers/{self.node_id}/status",
                json={"status": status, "last_heartbeat": datetime.now(timezone.utc).isoformat()},
                timeout=5
            )
            return resp.status_code in [200, 201]
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")
            return False

    def poll_assignments(self) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.post(f"{self.root_url}/work/claim", params={"node_id": self.node_id}, timeout=10)
            if resp.status_code in [200, 201]:
                return resp.json()
            return None
        except Exception:
            return None

    def claim_assignment(self, assignment_id: str) -> Optional[dict]:
        try:
            resp = self.session.post(f"{self.root_url}/assignments/{assignment_id}/claim",
                                      json={"node_id": self.node_id}, timeout=10)
            if resp.status_code in [200, 201]:
                return resp.json()
            return None
        except Exception as e:
            logger.warning(f"Claim error: {e}")
            return None

    def create_attempt(self, assignment_id: str) -> Optional[str]:
        try:
            resp = self.session.post(f"{self.root_url}/assignments/{assignment_id}/attempts",
                                      json={"node_id": self.node_id}, timeout=10)
            if resp.status_code in [200, 201]:
                return resp.json().get("attempt_id")
            return None
        except Exception:
            return None

    def submit_result(self, attempt_id: str, result: Dict[str, Any]) -> bool:
        try:
            output_text = result.get("output", "")
            if isinstance(output_text, str) and output_text.startswith('{'):
                result_dict = json.loads(output_text)
            else:
                result_dict = {"output": str(output_text)}
            result_dict["execution_evidence"] = result.get("execution_evidence", {})
            data = {"node_id": self.node_id, "result": result_dict,
                    "quality_score": result.get("quality_score", 0.85)}
            resp = self.session.post(f"{self.root_url}/attempts/{attempt_id}/result", json=data, timeout=10)
            return resp.status_code in [200, 201]
        except Exception as e:
            logger.warning(f"Result error: {e}")
            return False

    def fetch_task_spec(self, task_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(f"{self.root_url}/tasks/{task_id}", timeout=10)
            if resp.status_code == 200:
                td = resp.json()
                spec = td.get("specification", {})
                if isinstance(spec, str):
                    spec = json.loads(spec)
                return {"task_id": td.get("task_id"), "type": td.get("task_type"), "specification": spec}
            return None
        except Exception:
            return None

    def get_node_status(self) -> Optional[str]:
        try:
            resp = self.session.get(f"{self.root_url}/workers/{self.node_id}", timeout=10)
            if resp.status_code == 200:
                return resp.json().get("status")
            return None
        except Exception:
            return None

    def set_node_paused(self, reason: str) -> bool:
        try:
            resp = self.session.post(f"{self.root_url}/workers/{self.node_id}/status",
                                      json={"status": "paused", "reason": reason}, timeout=10)
            return resp.status_code in [200, 201]
        except Exception:
            return False


class OpenClawExecutor:
    """Executes tasks using actual OpenClaw via subprocess."""

    @staticmethod
    def format_task_with_bounded_learning(task_spec: dict, bounded_learning: list) -> str:
        learning_section = ""
        if bounded_learning:
            learning_section = "\n\n" + "=" * 70 + "\nRELEVANT PRIOR LEARNING\n" + "=" * 70 + "\n"
            for i, lr in enumerate(bounded_learning, 1):
                c = lr.get('content', {})
                stmt = c.get('statement', c.get('learning_statement', ''))
                learning_section += f"\n[Learning {i}] Statement: {stmt}\n"
            learning_section += "\n" + "=" * 70 + "\n"
        return f"""CURRENT TASK (Fabric assignment)
-----
{json.dumps(task_spec, indent=2)}{learning_section}

INSTRUCTIONS:
Execute the specified task.
If prior learning applies, use it as guidance.
Return your result with quality assessment."""

    @staticmethod
    def run_openclaw(prompt: str, task_id: str, test_id: str,
                     model: str = "deepseek/deepseek-v4-flash",
                     timeout_seconds: int = 600,
                     deadline_seconds: int = 0,
                     cap_at_stop: dict = None,
                     store: Optional['BudgetStateStore'] = None,
                     node_id: str = "",
                     budget_controller: Optional['BudgetController'] = None) -> str:
        """
        Run OpenClaw agent as subprocess with budget-compliant Popen + DeadlineWatchdog.

        Returns JSON string with task result.
        """
        # Save prompt for proof
        prompt_file = f"/tmp/actual_openclaw_prompt_{task_id}.txt"
        with open(prompt_file, 'w') as f:
            f.write("=" * 70 + f"\nACTUAL OpenClaw PROMPT (Task: {task_id})\n" + "=" * 70 + "\n\n")
            f.write(prompt)
            f.write("\n\n" + "=" * 70 + "\n")

        # Build command
        cmd = ["openclaw", "agent", "--agent", "executor", "--local",
               "--model", model, "--message", prompt,
               "--timeout", str(timeout_seconds), "--json"]

        # Popen (not subprocess.run) so watchdog can write reports on kill
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info(f"OpenClaw subprocess started (PID {proc.pid}). Timeout: {timeout_seconds}s")

        # Update inflight with PID
        if store and node_id:
            inflight = store.load_inflight(node_id)
            if inflight:
                inflight["pid"] = proc.pid
                store.write_inflight(node_id, inflight)

        # Start deadline watchdog if budget active
        watchdog = None
        if deadline_seconds > 0 and store and node_id and cap_at_stop:
            watchdog = DeadlineWatchdog(proc, task_id, node_id,
                                         deadline_seconds, store, cap_at_stop)
            watchdog.start()

        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            output = stdout.strip()
            logger.info(f"✓ OpenClaw agent completed (length: {len(output)} chars)")
            return json.dumps({
                "task_id": task_id,
                "test_id": test_id,
                "result": output,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "execution_evidence": {
                    "provider": "openclaw", "model": model,
                    "execution_type": "real local agent via CLI --local",
                    "success": True, "budget_controlled": budget_controller is not None,
                    "provider_confirmed": True
                }
            }, indent=2)
        else:
            logger.error(f"OpenClaw execution failed (code {proc.returncode}): {stderr}")
            raise Exception(f"OpenClaw error: {stderr[:500]}")


def execute_task_with_budget(task: Dict[str, Any], bounded_learning: list,
                               budget_config_obj: Optional[BudgetConfig],
                               budget_controller: Optional[BudgetController],
                               node_id: str,
                               store: Optional[BudgetStateStore]) -> Dict[str, Any]:
    """
    Execute task with full budget enforcement:
    - Estimate cost from prompt length + max_completion_tokens
    - Authorize before Popen
    - Write inflight JSON
    - Run OpenClaw with Popen + DeadlineWatchdog
    - On clean completion: remove inflight
    - On cap hit: write report, global pause, node pause
    """
    spec = task.get("specification", {})
    if isinstance(spec, str):
        spec = json.loads(spec)

    prompt = OpenClawExecutor.format_task_with_bounded_learning(spec, bounded_learning)
    task_id = task.get("task_id", "unknown")
    test_id = spec.get("test_id", "")

    if not (budget_controller and store and node_id):
        # No budget — run directly (legacy mode)
        return _execute_task_legacy(task, spec, prompt, task_id, test_id)

    model = budget_controller.config.default_model
    est_tokens, worst_cost = budget_controller.estimate_cost(prompt, model)

    # Set per-task deadline
    deadline_seconds = budget_controller.config.round_deadline_seconds
    budget_controller.deadline = time.time() + deadline_seconds

    # Reset per-task budget
    budget_controller.reset_task_budget()

    # Authorize (raises BudgetExceeded if denied — prevents Popen entirely)
    budget_controller.authorize(est_tokens, worst_cost)

    # Snapshot spend for inflight
    state_snapshot = store.read_state()
    cap_at_stop = {
        "run_tokens": state_snapshot.get("run_tokens", 0),
        "task_spend": state_snapshot.get("task_spend", 0),
        "daily_spend": state_snapshot.get("daily_spend", 0),
        "elapsed": 0
    }

    # Write inflight JSON (global_pause.flag NOT touched — only on cap hit)
    inflight_data = {
        "node_id": node_id,
        "task_id": task_id,
        "pid": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "deadline_at": datetime.fromtimestamp(
            budget_controller.deadline, tz=timezone.utc
        ).isoformat() if budget_controller.deadline else None,
        "worst_case_cost": worst_cost,
        "estimated_prompt_tokens": est_tokens,
        "model": model,
        "deadline_seconds": deadline_seconds,
        "task_budget_before": state_snapshot.get("task_spend", 0),
        "daily_budget_before": state_snapshot.get("daily_spend", 0)
    }
    store.write_inflight(node_id, inflight_data)

    logger.info(f"Budget OK — est ${worst_cost:.6f} ({est_tokens} tok). "
                f"Deadline: {deadline_seconds}s. Inflight: {node_id[:12]}...")

    # Run OpenClaw (will raise BudgetExceeded if watchdog fires)
    try:
        openclaw_output = OpenClawExecutor.run_openclaw(
            prompt, task_id, test_id,
            model=model,
            timeout_seconds=budget_controller.config.round_deadline_seconds,
            deadline_seconds=deadline_seconds,
            cap_at_stop=cap_at_stop,
            store=store,
            node_id=node_id,
            budget_controller=budget_controller
        )

        # Clean completion — remove inflight
        store.remove_inflight(node_id)
        logger.info(f"Inflight removed for node {node_id[:12]}...")

        return {
            "status": "completed",
            "output": openclaw_output,
            "quality_score": 0.85,
            "execution_evidence": {
                "provider": "openclaw", "model": model,
                "execution_type": "real local agent via CLI --local",
                "budget_controlled": True, "success": True
            }
        }
    except BudgetExceeded:
        # Watchdog fired — report already written, global_pause set
        return {
            "status": "failed",
            "error": "Budget cap exceeded during execution",
            "output": None,
            "quality_score": 0,
            "execution_evidence": {"budget_cap": "deadline"}
        }


def _execute_task_legacy(task: Dict[str, Any], spec: Dict[str, Any],
                         prompt: str, task_id: str, test_id: str) -> Dict[str, Any]:
    """Fallback when no budget controller is active."""
    try:
        output = OpenClawExecutor.run_openclaw(prompt, task_id, test_id)
        return {
            "status": "completed", "output": output, "quality_score": 0.85,
            "execution_evidence": {"provider": "openclaw", "success": True}
        }
    except Exception as e:
        return {
            "status": "failed", "error": str(e), "output": None,
            "quality_score": 0, "execution_evidence": {"error": str(e)}
        }


class ExecutorAdapter:
    def __init__(self, budget_config_path: str = None):
        self.config = ExecutorConfig()
        self.client = FabricClient(self.config.fabric_url, self.config.node_id)
        self.running = False
        self.last_heartbeat = 0

        # Budget controls
        self.budget_config = None
        self.budget_store = None
        self.budget_controller = None
        if budget_config_path and os.path.exists(budget_config_path):
            self.budget_config = BudgetConfig(budget_config_path)
            self.budget_store = BudgetStateStore(os.environ.get("BUDGET_DIR", DEFAULT_BUDGET_DIR))
            self.budget_controller = BudgetController(self.budget_config, self.budget_store, self.config.node_id)
            logger.info(f"Budget controls active — config: {budget_config_path}")

    def start(self):
        logger.info(f"Starting OpenClaw Executor Adapter (node: {self.config.node_id[:12]}...)")
        logger.info(f"Fabric URL: {self.config.fabric_url}")

        # === BUDGET STARTUP CHECKS (read-only) ===
        if self.budget_store:
            # 1. Global pause
            if self.budget_store.is_global_paused():
                logger.error("Global pause flag active — all runners blocked. Clear flag to resume.")
                return

            # 2. Orphan inflight scan
            orphaned = False
            for inflight in self.budget_store.scan_inflight():
                pid = inflight.get("pid")
                task_id = inflight.get("task_id", "unknown")
                inode_id = inflight.get("node_id", "unknown")
                if pid and pid > 0:
                    try:
                        os.kill(pid, 0)
                        logger.info(f"Inflight task {task_id} (PID {pid}) still running — skipping")
                        continue
                    except (ProcessLookupError, PermissionError):
                        pass
                logger.error(f"Orphan inflight: {task_id} (node {inode_id[:12]}..., PID {pid})")
                state = BudgetState("orphan", task_id, inode_id,
                                    {"run_tokens": 0, "task_spend": 0, "daily_spend": 0},
                                    "startup_orphan_scan")
                self.budget_store.write_report(state)
                self.budget_store.set_global_pause()
                orphaned = True
            if orphaned:
                logger.error("Orphans found. Global pause set. Human must investigate.")
                return

            # 3. Node status
            status = self.client.get_node_status()
            if status == "paused":
                logger.error(f"Node {self.config.node_id[:12]}... is paused. Must POST available to resume.")
                return

        # Registration check
        if not self.client.check_node_registered():
            logger.error(f"Node {self.config.node_id[:12]}... not registered")
            return

        self.running = True
        self._run_loop()

    def _run_loop(self):
        logger.info("Entering main loop, polling for assignments...")
        try:
            while self.running:
                if time.time() - self.last_heartbeat > self.config.config["heartbeat_interval"]:
                    self.client.send_heartbeat("available")
                    self.last_heartbeat = time.time()
                assignment = self.client.poll_assignments()
                if assignment:
                    self._handle_assignment(assignment)
                time.sleep(self.config.config["poll_interval"])
        except KeyboardInterrupt:
            self.running = False
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise

    def _handle_assignment(self, assignment: Dict[str, Any]) -> bool:
        assignment_id = assignment.get("assignment_id")
        task_id = assignment.get("task_id")
        logger.info(f"Received assignment: {assignment_id} (task: {task_id})")

        try:
            task = self.client.fetch_task_spec(task_id)
            if not task:
                logger.error(f"Task {task_id} not found")
                return False

            # Claim
            status = assignment.get("status", "")
            if status == "claimed":
                claim_response = assignment
            else:
                claim_response = self.client.claim_assignment(assignment_id)
                if not claim_response:
                    return False

            bounded_learning = claim_response.get("bounded_learning_context", [])

            # Get attempt_id
            attempt_id = claim_response.get("attempt_id")
            if not attempt_id:
                try:
                    assign_resp = self.client.session.get(
                        f"{self.client.root_url}/assignments/{assignment_id}", timeout=10)
                    if assign_resp.status_code == 200:
                        for att in assign_resp.json().get("attempts", []):
                            if att.get("status") in ("running", "in_progress"):
                                attempt_id = att.get("attempt_id")
                                break
                except Exception:
                    pass
            if not attempt_id:
                try:
                    cr = self.client.session.post(
                        f"{self.client.root_url}/assignments/{assignment_id}/attempts",
                        json={"node_id": self.client.node_id}, timeout=10)
                    if cr.status_code in (200, 201):
                        attempt_id = cr.json().get("attempt_id")
                except Exception:
                    pass
            if not attempt_id:
                return False

            # Execute with budget
            result = execute_task_with_budget(
                task, bounded_learning,
                self.budget_config, self.budget_controller,
                self.config.node_id, self.budget_store
            )

            # Check for budget cap
            ee = result.get("execution_evidence", {})
            if ee.get("budget_cap"):
                logger.error(f"Budget cap: {ee['budget_cap']}")
                if self.budget_store:
                    spend = ee.get("spend_at_stop", {})
                    state = BudgetState(ee["budget_cap"], task_id, self.config.node_id, spend, "pre_model_call")
                    self.budget_store.write_report(state)
                    self.budget_store.set_global_pause()
                    self.client.set_node_paused(f"Budget cap: {ee['budget_cap']}")
                return False

            # Submit result
            if self.client.submit_result(attempt_id, result):
                logger.info(f"Assignment {assignment_id} completed")
                return True
            logger.error(f"Result submission failed for {attempt_id}")
            return False
        except Exception as e:
            logger.error(f"Error handling {assignment_id}: {e}")
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OpenClaw Executor with Budget Controls")
    parser.add_argument("--assignment-id", type=str, help="Handle only this assignment")
    parser.add_argument("--budget-config", type=str, default=None, help="Path to budget.json")
    args = parser.parse_args()

    adapter = ExecutorAdapter(budget_config_path=args.budget_config)
    try:
        if args.assignment_id:
            logger.info(f"BOUNDED MODE: assignment {args.assignment_id}")
            cr = adapter.client.claim_assignment(args.assignment_id)
            if cr:
                # Get task_id from assignment
                try:
                    resp = adapter.client.session.get(f"{adapter.client.root_url}/assignments/{args.assignment_id}", timeout=10)
                    task_id = resp.json().get("task_id") if resp.status_code == 200 else cr.get("task_id")
                except Exception:
                    task_id = cr.get("task_id")

                if task_id:
                    task = adapter.client.fetch_task_spec(task_id)
                    if task:
                        ad = {"assignment_id": args.assignment_id, "task_id": task_id,
                              "node_id": adapter.config.node_id, "status": "claimed"}
                        if adapter._handle_assignment(ad):
                            logger.info("Bounded assignment completed")
                        else:
                            logger.error("Bounded assignment FAILED")
                            sys.exit(1)
                    else:
                        logger.error(f"Failed to fetch task spec for {task_id}")
                else:
                    logger.error(f"No task_id for {args.assignment_id}")
            else:
                logger.error(f"Failed to claim {args.assignment_id}")
        else:
            adapter.start()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()