#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
trap 'echo; echo "The app stopped. Read the error above."; read -r -p "Press Return to close."; exit 1' ERR
if [ ! -x .venv/bin/python ]; then
  echo "Please double-click Setup Mac.command first."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Opening Dunkin Price Agent. Keep this window open while the app is running."
.venv/bin/python -X utf8 -m dunkin_compare.desktop
