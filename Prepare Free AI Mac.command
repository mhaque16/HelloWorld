#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
trap 'echo; echo "Free AI setup stopped. Read the message above."; read -r -p "Press Return to close."; exit 1' ERR
DPC_OLLAMA=""
for DPC_CANDIDATE in ollama /usr/local/bin/ollama /opt/homebrew/bin/ollama /Applications/Ollama.app/Contents/Resources/ollama; do
  if command -v "$DPC_CANDIDATE" >/dev/null 2>&1; then DPC_OLLAMA="$DPC_CANDIDATE"; break; fi
done
if [ -z "$DPC_OLLAMA" ]; then
  echo "First install Ollama from https://ollama.com/download/mac and open its app."
  echo "Then double-click Prepare Free AI Mac.command again. No API key is needed."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Open the Ollama app before continuing."
echo "This downloads the Gemma 3 4B vision model (several GB) for local use."
echo "16 GB or more memory is recommended. Inference may be slow on smaller/Intel Macs."
read -r -p "Press Return to download, or Control-C to cancel."
"$DPC_OLLAMA" pull gemma3:4b
echo "Free local model is ready. In the agent's AI settings choose Free local (Ollama)."
read -r -p "Press Return to close."
