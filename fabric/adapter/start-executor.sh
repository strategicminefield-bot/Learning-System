#!/bin/bash
# Start OpenClaw Executor Adapter

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ADAPTER_PY="$SCRIPT_DIR/openclaw_executor.py"

echo "================================"
echo "OpenClaw Executor Adapter"
echo "================================"
echo ""
echo "Starting adapter from: $ADAPTER_PY"
echo ""

# Ensure config directory exists
mkdir -p ~/.openclaw

# Run adapter
python3 "$ADAPTER_PY"
