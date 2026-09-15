#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-all}"

echo "=== Learning System Build ==="
echo "Target: $TARGET"

case "$TARGET" in
  foundation|workers|learning|all)
    echo "Build target '$TARGET' selected."
    ;;
  *)
    echo "Unknown target: $TARGET"
    echo "Valid targets: foundation workers learning all"
    exit 1
    ;;
esac

echo "Build framework ready."
