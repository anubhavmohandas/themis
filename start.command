#!/usr/bin/env bash
# Double-click on macOS (or run ./start.command on Linux). Launches run.py.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 run.py
else
  echo "Python 3 not found. Install it from https://www.python.org/downloads/"
fi
read -n 1 -s -r -p "Press any key to close..."
