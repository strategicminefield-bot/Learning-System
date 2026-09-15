#!/usr/bin/env bash
set -euo pipefail

echo "=== Learning System Verification ==="

test -d docs
test -d bootstrap
test -d scripts
test -d fabric
test -d workers
test -d migrations
test -d tests
test -d config

echo "Repository structure verified."
