#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"

echo "=== Learning System VPS Bootstrap ==="
echo "Host: $VPS"
echo "Directory: $REMOTE_DIR"

ssh "$VPS" "mkdir -p $REMOTE_DIR/{api,config,migrations,backups,logs}"

echo "VPS directories ready."
