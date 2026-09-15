#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"

echo "=== Learning System Remote Status ==="

ssh "$VPS" "
echo 'Host:'
hostname
echo
echo 'Learning Fabric:'
test -d $REMOTE_DIR && echo 'DIRECTORY OK' || echo 'DIRECTORY MISSING'
echo
echo 'API health:'
curl -sf http://127.0.0.1:8000/health || echo 'API UNAVAILABLE'
echo
echo 'Database health:'
curl -sf http://127.0.0.1:8000/db/health || echo 'DATABASE UNAVAILABLE'
"
