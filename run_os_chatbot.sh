#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p logs
if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/venv/bin/activate"
fi
export PYTHONUNBUFFERED=1
exec python app.py >> "$SCRIPT_DIR/logs/os_chatbot.log" 2>&1
