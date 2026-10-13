#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
trap 'echo; echo "Setup stopped. Read the error above and try again."; read -r -p "Press Return to close."; exit 1' ERR
echo "Setting up Dunkin Price Agent for Mac..."
DPC_PYTHON=""
for DPC_CANDIDATE in python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$DPC_CANDIDATE" >/dev/null 2>&1 && "$DPC_CANDIDATE" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,12) else 1)' >/dev/null 2>&1; then
    DPC_PYTHON="$DPC_CANDIDATE"
    break
  fi
done
if [ -z "$DPC_PYTHON" ]; then
  echo "Install Python 3.12 or newer using the macOS installer at python.org/downloads/macos/."
  echo "The python.org installer includes the desktop window support this app needs."
  read -r -p "Press Return to close, install Python, then open Setup Mac.command again."
  exit 1
fi
"$DPC_PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if ! .venv/bin/python -m playwright install chromium; then
  echo "Chromium could not be downloaded. The app can also try Google Chrome if installed."
fi
.venv/bin/python -m unittest discover -s tests -v
echo
echo "Setup complete! Double-click Open Agent Mac.command to open the app."
read -r -p "Press Return to close."
