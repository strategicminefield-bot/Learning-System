#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"

echo "=== Learning System Launch Check ==="

./verify.sh
./test.sh
./scripts/remote-status.sh
./scripts/verify-remote.sh

echo
echo "=== LAUNCH CHECK PASSED ==="
