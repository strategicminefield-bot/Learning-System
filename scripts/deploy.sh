#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"

echo "=== Deploying Learning System ==="

git pull --ff-only origin main

./verify.sh
./test.sh

ssh "$VPS" "mkdir -p $REMOTE_DIR"

rsync -az --delete \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  ./ "$VPS:$REMOTE_DIR/"

echo "=== Deployment complete ==="
