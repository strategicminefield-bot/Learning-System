#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"

echo "=== Deploying Learning Fabric API ==="

scp fabric/api/main.py "$VPS:$REMOTE_DIR/api/main.py"

ssh "$VPS" "
set -e
python3 -m py_compile '$REMOTE_DIR/api/main.py'
docker cp '$REMOTE_DIR/api/main.py' learning-fabric-api:/app/main.py
docker restart learning-fabric-api >/dev/null
sleep 3
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8000/db/health
echo
echo 'API DEPLOYMENT PASSED'
"
