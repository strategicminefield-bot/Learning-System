"""
Budget Controller for Learning Fabric Executor Nodes.

Three-layer enforcement:
1. Adapter pre-invocation gate (this module)
2. Dedicated executor OpenRouter key with hard credit limit
3. Main/account OpenRouter backstop

This module handles Layer 1 only.
"""

import json
import os
import time
import fcntl
import signal
import sys
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)

# Default paths — override via BUDGET_DIR env var or config argument
DEFAULT_BUDGET_DIR = "/opt/lf-budget"


class BudgetConfig:
    """Loads budget configuration from a JSON file."""

    def __init__(self, config_path: str):
        with open(config_path) as f:
            self._data = json.load(f)

    @property
    def per_run_token_cap(self) -> int:
        return self._data.get("per_run_token_cap", 20000)

    @property
    def per_task_budget_usd(self) -> float:
        return self._data.get("per_task_budget_usd", 1.00)

    @property
    def round_deadline_seconds(self) -> int:
        return self._data.get("round_deadline_seconds", 600)

    @property
    def daily_ceiling_usd(self) -> float:
        return self._data.get("daily_ceiling_usd", 5.00)

    @property
    def max_concurrent_nodes(self) -> int:
        return self._data.get("max_concurrent_nodes", 3)

    @property
    def daily_reset_utc(self) -> str:
        return self._data.get("daily_reset_utc", "00:00")

    @property
    def max_completion_tokens(self) -> int:
        return self._data.get("max_completion_tokens", 8000)

    @property
    def default_model(self) -> str:
        return self._data.get("default_model", "deepseek/deepseek-v4-flash")

    def price_per_mtok(self, model: str = None) -> float:
        model = model or self.default_model
        prices = self._data.get("model_prices_per_mtok", {})
        return prices.get(model, 0.15)  # fallback price

    def price_per_token(self, model: str = None) -> float:
        return self.price_per_mtok(model) / 1_000_000


class BudgetState:
    """Snapshot of a cap-hit event, written as a report."""

    def __init__(self, cap_type: str, task_id: str, node_id: str,
                 spend: Dict[str, Any], last_action: str,
                 estimated_call_cost: float = 0):
        self.cap_type = cap_type
        self.task_id = task_id
        self.node_id = node_id
        self.spend = spend
        self.last_action = last_action
        self.estimated_call_cost = estimated_call_cost
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "cap_type": self.cap_type,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "spend_at_stop": self.spend,
            "estimated_call_cost": self.estimated_call_cost,
            "last_action": self.last_action,
            "timestamp": self.timestamp
        }


class BudgetExceeded(Exception):
    """Raised when a budget cap is hit before a model call."""
    def __init__(self, state: BudgetState):
        self.state = state
        super().__init__(f"Budget cap hit: {state.cap_type}")


class BudgetStateStore:
    """Persists budget state to disk with fcntl file locking.

    Manages:
    - budget_state.json: daily_spend, daily_date, run_tokens, task_spend
    - inflight/ directory: one file per running node
    - reports/ directory: one report per cap hit
    - global_pause.flag: sentinel file
    """

    def __init__(self, budget_dir: str = DEFAULT_BUDGET_DIR):
        self.budget_dir = Path(budget_dir)
        self.budget_dir.mkdir(parents=True, exist_ok=True)
        (self.budget_dir / "inflight").mkdir(exist_ok=True)
        (self.budget_dir / "reports").mkdir(exist_ok=True)
        self.state_path = self.budget_dir / "budget_state.json"
        self.flag_path = self.budget_dir / "global_pause.flag"
        self._init_state()

    def _init_state(self):
        if not self.state_path.exists():
            with open(self.state_path, 'w') as f:
                json.dump({
                    "daily_spend": 0.0,
                    "daily_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "run_tokens": 0,
                    "task_spend": 0.0,
                    "last_cap": None,
                    "node_paused": False
                }, f)

    def _ensure_date_reset(self, state: dict) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.get("daily_date") != today:
            state["daily_spend"] = 0.0
            state["daily_date"] = today
        return state

    def atomic_update(self, mutator_fn: Callable[[dict], None]) -> dict:
        """Read state, apply mutator, write back — with exclusive lock."""
        with open(self.state_path, 'r+') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            state = json.load(f)
            state = self._ensure_date_reset(state)
            mutator_fn(state)
            f.seek(0)
            json.dump(state, f, indent=2)
            f.truncate()
            os.fsync(f.fileno())
            return state

    def read_state(self) -> dict:
        """Read current state with shared lock."""
        with open(self.state_path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            state = json.load(f)
            return self._ensure_date_reset(state)

    def write_report(self, state: BudgetState):
        path = self.budget_dir / "reports" / f"{state.task_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
        with open(path, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)
        logger.info(f"Budget report written: {path}")

    def set_global_pause(self):
        self.flag_path.touch()
        logger.info("Global pause flag set — all runners blocked")

    def clear_global_pause(self):
        if self.flag_path.exists():
            self.flag_path.unlink()
            logger.info("Global pause flag cleared")

    def is_global_paused(self) -> bool:
        return self.flag_path.exists()

    def inflight_path(self, node_id: str) -> Path:
        return self.budget_dir / "inflight" / f"{node_id}.json"

    def write_inflight(self, node_id: str, data: dict):
        path = self.inflight_path(node_id)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def remove_inflight(self, node_id: str):
        path = self.inflight_path(node_id)
        if path.exists():
            path.unlink()

    def load_inflight(self, node_id: str) -> Optional[dict]:
        path = self.inflight_path(node_id)
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def scan_inflight(self) -> list:
        inflight_dir = self.budget_dir / "inflight"
        results = []
        for fname in os.listdir(str(inflight_dir)):
            if fname.endswith(".json"):
                path = inflight_dir / fname
                with open(path) as f:
                    data = json.load(f)
                results.append(data)
        return results


class BudgetController:
    """Per-adapter budget enforcement instance."""

    def __init__(self, config: BudgetConfig, store: BudgetStateStore,
                 node_id: str):
        self.config = config
        self.store = store
        self.node_id = node_id
        self.deadline = None  # Set per-assignment, not at init

    def estimate_cost(self, prompt: str, model: str = None) -> tuple:
        """Returns (estimated_tokens, worst_case_cost)."""
        est_prompt_tokens = int(len(prompt) * 1.5) + 1  # safe overestimate
        max_completion = self.config.max_completion_tokens
        total_estimated = est_prompt_tokens + max_completion
        price = self.config.price_per_token(model)
        cost = total_estimated * price
        return est_prompt_tokens, cost

    def authorize(self, estimated_tokens: int, estimated_cost: float):
        """Check caps and deduct provisionally. Raises BudgetExceeded if denied."""

        def _check(state: dict):
            # Check per-run token cap
            run_tokens = state.get("run_tokens", 0)
            if run_tokens + estimated_tokens > self.config.per_run_token_cap:
                raise BudgetExceeded(BudgetState(
                    "token_cap", "", self.node_id,
                    {"run_tokens": run_tokens, "task_spend": 0, "daily_spend": state.get("daily_spend", 0)},
                    "pre_model_call"
                ))

            # Check per-task budget (within a single _handle_assignment)
            # task_spend resets per assignment
            task_spend = state.get("task_spend", 0)
            if task_spend + estimated_cost > self.config.per_task_budget_usd:
                raise BudgetExceeded(BudgetState(
                    "task_budget", "", self.node_id,
                    {"run_tokens": run_tokens + estimated_tokens,
                     "task_spend": task_spend, "daily_spend": state.get("daily_spend", 0)},
                    "pre_model_call",
                    estimated_call_cost=estimated_cost
                ))

            # Check daily ceiling
            daily_spend = state.get("daily_spend", 0)
            if daily_spend + estimated_cost > self.config.daily_ceiling_usd:
                raise BudgetExceeded(BudgetState(
                    "daily_ceiling", "", self.node_id,
                    {"run_tokens": run_tokens + estimated_tokens,
                     "task_spend": task_spend, "daily_spend": daily_spend},
                    "pre_model_call",
                    estimated_call_cost=estimated_cost
                ))

            # Provisional deduct
            state["run_tokens"] = run_tokens + estimated_tokens
            state["task_spend"] = task_spend + estimated_cost
            state["daily_spend"] = daily_spend + estimated_cost

        self.store.atomic_update(_check)
        logger.info(f"Budget OK — provisionally deducted ${estimated_cost:.6f} ({estimated_tokens} tok)")

    def check_deadline(self) -> bool:
        """Returns True if deadline has passed."""
        if self.deadline is None:
            return False
        return time.time() > self.deadline

    def reset_task_budget(self):
        """Reset per-task budget for a new assignment."""

        def _reset(state: dict):
            state["task_spend"] = 0.0
            state["run_tokens"] = 0

        self.store.atomic_update(_reset)


class DeadlineWatchdog(threading.Thread):
    """Daemon thread that kills the subprocess if it exceeds the deadline.

    Also writes budget report, sets global pause, and pauses the node.
    """

    def __init__(self, proc: "subprocess.Popen", task_id: str, node_id: str,
                 deadline_seconds: int, store: BudgetStateStore,
                 cap_at_stop: dict):
        super().__init__(daemon=True)
        self.proc = proc
        self.task_id = task_id
        self.node_id = node_id
        self.deadline_seconds = deadline_seconds
        self.store = store
        self.cap_at_stop = cap_at_stop
        self.started_at = time.time()

    def run(self):
        deadline = time.time() + self.deadline_seconds
        while time.time() < deadline + 30:
            time.sleep(1)
            if self.proc.poll() is not None:
                return  # completed naturally

        # Past deadline — kill the subprocess
        logger.warning(f"Deadline exceeded for task {self.task_id}. Killing subprocess.")
        self.proc.send_signal(signal.SIGTERM)
        time.sleep(5)
        if self.proc.poll() is None:
            self.proc.kill()

        # Write report
        state = BudgetState(
            "deadline", self.task_id, self.node_id,
            self.cap_at_stop,
            "deadline_kill"
        )
        self.store.write_report(state)

        # Set pauses
        self.store.set_global_pause()

        # Log and exit
        logger.error(f"Deadline kill complete. Task {self.task_id} terminated.")
        os._exit(1)