#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"

echo "=== Learning Fabric End-to-End Test ==="

REQUEST_ID="$(
ssh "$VPS" "curl -sf -X POST http://127.0.0.1:8000/requests \
  -H 'Content-Type: application/json' \
  -d '{\"request_type\":\"system_test\",\"content\":{\"task\":\"Reply with exactly: LEARNING FABRIC TEST PASSED\"}}'" |
python3 -c "import sys,json; print(json.load(sys.stdin)['request_id'])"
)"

echo "Request: $REQUEST_ID"

echo
echo "Request created successfully."
echo "The worker must now claim and complete this request."
