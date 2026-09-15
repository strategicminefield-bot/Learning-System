#!/usr/bin/env bash
set -euo pipefail

echo "=== Learning System Status ==="
echo
echo "Git:"
git status --short --branch
echo
echo "Repository:"
git log -1 --oneline
echo
echo "Directories:"
find . -maxdepth 1 -type d | sort
