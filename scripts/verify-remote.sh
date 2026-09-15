#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"

echo "=== Remote Verification ==="

ssh "$VPS" "
set -e
test -d '$REMOTE_DIR'
test -f '$REMOTE_DIR/api/main.py'
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8000/db/health
echo
echo 'REMOTE VERIFICATION PASSED'
"
