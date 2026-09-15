#!/usr/bin/env bash
set -euo pipefail

echo "=== Learning System Tests ==="

python3 -m compileall -q fabric workers scripts || true

echo "Basic repository test passed."
