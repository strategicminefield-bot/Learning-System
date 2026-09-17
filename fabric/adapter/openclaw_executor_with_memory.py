#!/usr/bin/env python3
"""
OpenClaw Executor with System Memory Integration (Section 25)

Implements node reconstitution after context loss:
1. Load persistent identity from ~/.openclaw/executor_config.json
2. Call Fabric's POST /api/v1/nodes/{node_id}/reconstitute?reason=startup
3. Extract bootstrap, system_memory, procedures
4. Resume execution from checkpoints if available
5. Save work state checkpoints for recovery

This executor can lose conversational context, restart, or be replaced.
It recovers operational state from the Fabric, not from chat history.
"""

import os
import sys
import json
import time
import uuid
import logging
import subprocess
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIG PATHS
# ============================================================

CONFIG_DIR = Path.home() / ".openclaw"
CONFIG_FILE = CONFIG_DIR / "executor_config.json"
EXECUTION_LOG = Path("/tmp/openclaw/execution.log")
MEMORY_LOG = Path("/tmp/openclaw/memory.log")


# ============================================================
# NODE IDENTITY & BOOTSTRAP
# ============================================================

class ExecutorIdentity:
    """Load and manage persistent node identity."""
    
    @staticmethod
    def load_or_create():
        """Load identity from disk, or create if missing."""
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                return config.get("node_id"), config.get("fabric_url")
        
        # Create new identity
        node_id = str(uuid.uuid4())
        logger.info(f"Creating new executor identity: {node_id}")
        
        config = {
            "node_id": node_id,
            "fabric_url": os.environ.get("FABRIC_URL", "http://95.179.236.41:8000"),
            "adapter_type": "openclaw",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Identity saved to {CONFIG_FILE}")
        return node_id, config["fabric_url"]


# ============================================================
# RECONSTITUTION LOGIC
# ============================================================

class Reconstitution:
    """Retrieve and apply reconstitution package from Fabric."""
    
    def __init__(self, fabric_url: str, node_id: str):
        self.fabric_url = fabric_url
        self.node_id = node_id
        self.api_base = f"{fabric_url}/api/v1"
    
    def request_package(self, reason: str = "startup") -> Optional[Dict[str, Any]]:
        """
        Request reconstitution package from Fabric.
        
        Reason: 'startup', 'context_loss', 'restart', etc.
        Returns: reconstitution package with bootstrap, memory, procedures
        """
        url = f"{self.api_base}/nodes/{self.node_id}/reconstitute"
        
        try:
            logger.info(f"Requesting reconstitution package (reason: {reason})")
            resp = requests.post(url, params={"reason": reason}, timeout=10)
            resp.raise_for_status()
            
            package = resp.json()
            logger.info(f"✓ Reconstitution package received ({len(package)} keys)")
            self._log_memory_access("reconstitution_package", reason, len(package))
            
            return package
        except Exception as e:
            logger.error(f"✗ Failed to get reconstitution package: {e}")
            return None
    
    def apply_bootstrap(self, package: Dict) -> bool:
        """Extract and validate bootstrap info from package."""
        try:
            bootstrap = package.get("bootstrap", {})
            logger.info(f"Bootstrap adapter: {bootstrap.get('adapter_type')} v{bootstrap.get('adapter_version')}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply bootstrap: {e}")
            return False
    
    def get_system_memory(self, package: Dict) -> Dict[str, Any]:
        """Extract system memory from package."""
        memory = {}
        for mem in package.get("system_memory", []):
            mem_type = mem.get("type")
            memory[mem_type] = mem.get("content", {})
            logger.info(f"  Loaded memory: {mem_type}")
        return memory
    
    def get_procedures(self, package: Dict) -> list:
        """Extract procedures from package."""
        procedures = package.get("procedures", [])
        logger.info(f"  Loaded {len(procedures)} procedures")
        return procedures
    
    def get_work_in_progress(self, package: Dict) -> Optional[Dict]:
        """Check if there's work in progress to resume."""
        work = package.get("current_work")
        if work:
            logger.info(f"  Work in progress: {work.get('assignment_id')}")
        return work
    
    def _log_memory_access(self, access_type: str, reason: str, items: int):
        """Log memory access for observability."""
        MEMORY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MEMORY_LOG, "a") as f:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "node_id": self.node_id,
                "access_type": access_type,
                "reason": reason,
                "items": items,
            }
            f.write(json.dumps(log_entry) + "\n")


# ============================================================
# WORK STATE CHECKPOINTING
# ============================================================

class WorkCheckpoint:
    """Save and recover work state across context loss."""
    
    def __init__(self, fabric_url: str, node_id: str):
        self.fabric_url = fabric_url
        self.node_id = node_id
        self.api_base = f"{fabric_url}/api/v1"
    
    def save(self, assignment_id: str, task_id: str, attempt_id: str,
             stage: str, data: Dict) -> bool:
        """Save current work state for recovery."""
        url = f"{self.api_base}/nodes/{self.node_id}/work-checkpoint"
        
        payload = {
            "assignment_id": assignment_id,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "checkpoint_stage": stage,
            "checkpoint_data": data,
        }
        
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logger.debug(f"Work checkpoint saved: {stage}")
            return True
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")
            return False
    
    def recover(self) -> Optional[Dict]:
        """Retrieve latest work checkpoint."""
        url = f"{self.api_base}/nodes/{self.node_id}/work-checkpoint"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                checkpoint = resp.json()
                logger.info(f"Work checkpoint recovered: {checkpoint.get('checkpoint_stage')}")
                return checkpoint
            elif resp.status_code == 404:
                logger.info("No work checkpoint to recover")
                return None
        except Exception as e:
            logger.warning(f"Failed to recover checkpoint: {e}")
        
        return None


# ============================================================
# EXECUTION ENGINE (simplified from main adapter)
# ============================================================

class ExecutionEngine:
    """Execute tasks using OpenClaw local agent."""
    
    def __init__(self, memory_package: Dict):
        self.memory = memory_package
        self.role = self.memory.get("node_role", {})
        self.capabilities = self.role.get("capabilities", [])
    
    def execute_task(self, prompt: str) -> Dict[str, Any]:
        """
        Execute a task via OpenClaw local agent.
        
        Returns: {
            "success": bool,
            "output": str,
            "error": Optional[str],
            "execution_time": float,
            "model": str,
            "provider": "openclaw"
        }
        """
        start_time = time.time()
        
        try:
            logger.info(f"Executing task via OpenClaw...")
            
            # Call openclaw CLI
            result = subprocess.run(
                ["openclaw", "agent", "--local", "--message", prompt],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            execution_time = time.time() - start_time
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": None,
                    "execution_time": execution_time,
                    "model": "local-openclaw",
                    "provider": "openclaw",
                }
            else:
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": result.stderr,
                    "execution_time": execution_time,
                    "model": "local-openclaw",
                    "provider": "openclaw",
                }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "error": "Execution timeout (300s)",
                "execution_time": time.time() - start_time,
                "model": "local-openclaw",
                "provider": "openclaw",
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time": time.time() - start_time,
                "model": "local-openclaw",
                "provider": "openclaw",
            }


# ============================================================
# MAIN EXECUTOR LOOP WITH MEMORY
# ============================================================

def main():
    logger.info("=" * 70)
    logger.info("OpenClaw Executor with System Memory Integration (Section 25)")
    logger.info("=" * 70)
    
    # Step 1: Load persistent identity
    logger.info("\n[1] Loading persistent node identity...")
    node_id, fabric_url = ExecutorIdentity.load_or_create()
    logger.info(f"✓ Node ID: {node_id}")
    logger.info(f"✓ Fabric URL: {fabric_url}")
    
    # Step 2: Request reconstitution package
    logger.info("\n[2] Requesting reconstitution package from Fabric...")
    reconstitution = Reconstitution(fabric_url, node_id)
    package = reconstitution.request_package(reason="startup")
    
    if not package:
        logger.error("✗ Failed to get reconstitution package. Exiting.")
        sys.exit(1)
    
    # Step 3: Apply bootstrap & extract memory
    logger.info("\n[3] Applying bootstrap configuration...")
    reconstitution.apply_bootstrap(package)
    
    logger.info("\n[4] Loading system memory...")
    system_memory = reconstitution.get_system_memory(package)
    
    logger.info("\n[5] Loading procedures...")
    procedures = reconstitution.get_procedures(package)
    
    # Step 4: Check for work in progress
    logger.info("\n[6] Checking for work in progress...")
    work_in_progress = reconstitution.get_work_in_progress(package)
    
    checkpoint_recovery = None
    if work_in_progress and not work_in_progress.get("assignment_id"):
        logger.info("\n[7] Attempting to recover work checkpoint...")
        checkpoint_mgr = WorkCheckpoint(fabric_url, node_id)
        checkpoint_recovery = checkpoint_mgr.recover()
    
    # Step 5: Initialize execution engine
    logger.info("\n[8] Initializing execution engine...")
    executor = ExecutionEngine(system_memory)
    logger.info(f"✓ Capabilities: {', '.join(executor.capabilities)}")
    
    # Step 6: Ready for work
    logger.info("\n" + "=" * 70)
    logger.info("✓ EXECUTOR READY - Awaiting assignments")
    logger.info(f"  Node ID: {node_id}")
    logger.info(f"  Identity persisted at: {CONFIG_FILE}")
    logger.info(f"  Can recover from: POST {fabric_url}/api/v1/nodes/{node_id}/reconstitute")
    logger.info(f"  Memory sources: bootstrap, system_memory, procedures, work_checkpoints")
    logger.info("=" * 70 + "\n")
    
    # Test execution (if a prompt is provided)
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        logger.info(f"Executing test prompt: {prompt}\n")
        
        result = executor.execute_task(prompt)
        
        logger.info(f"\n{'=' * 70}")
        logger.info(f"Execution Result:")
        logger.info(f"  Success: {result['success']}")
        logger.info(f"  Time: {result['execution_time']:.2f}s")
        logger.info(f"  Provider: {result['provider']}")
        logger.info(f"  Output: {result['output'][:200]}..." if len(result['output']) > 200 else f"  Output: {result['output']}")
        if result['error']:
            logger.info(f"  Error: {result['error']}")
        logger.info(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
