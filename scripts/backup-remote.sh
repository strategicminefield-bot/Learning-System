#!/usr/bin/env bash
set -euo pipefail

VPS="${VPS:-vultr}"
REMOTE_DIR="/opt/learning-fabric"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

ssh "$VPS" "
set -e
mkdir -p '$REMOTE_DIR/backups'
tar -czf '$REMOTE_DIR/backups/learning-fabric-$TIMESTAMP.tar.gz' \
  --exclude='backups' \
  '$REMOTE_DIR'
echo 'REMOTE BACKUP CREATED'
"

git add scripts/backup-remote.sh
git commit -m "Add automated remote backup"
git push origin main
