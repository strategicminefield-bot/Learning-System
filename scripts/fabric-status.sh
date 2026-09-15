#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"

echo "=== Learning Fabric Status ==="

ssh "$VPS" "
echo 'API:'
curl -sf http://127.0.0.1:8000/health
echo

echo 'Database:'
curl -sf http://127.0.0.1:8000/db/health
echo

echo 'Endpoints:'
curl -sf http://127.0.0.1:8000/openapi.json | \
python3 -c \"import sys,json; print('\\n'.join(sorted(json.load(sys.stdin)['paths'])))\"
"

echo
echo "=== STATUS CHECK COMPLETE ==="
