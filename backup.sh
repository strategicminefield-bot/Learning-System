#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/learning-system-backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

tar \
  --exclude='.git' \
  --exclude='__pycache__' \
  -czf "$BACKUP_DIR/Learning-System-$TIMESTAMP.tar.gz" .

echo "Backup created:"
echo "$BACKUP_DIR/Learning-System-$TIMESTAMP.tar.gz"
