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
echo "This downloads the Gemma 3 4B vision model (several GB) for local use."
echo "16 GB or more memory is recommended. Inference may be slow on smaller/Intel Macs."
read -r -p "Press Return to download, or Control-C to cancel."
function dpc_server_ready() {
  curl --silent --fail --max-time 2 --noproxy '*' http://127.0.0.1:11434/api/tags >/dev/null 2>&1
}
if ! dpc_server_ready; then
  echo "Starting Ollama..."
  if ! open -a Ollama >/dev/null 2>&1; then
    echo "Ollama app was not found. Starting the installed local server instead."
    mkdir -p logs
    OLLAMA_HOST=127.0.0.1:11434 nohup "$DPC_OLLAMA" serve >logs/ollama_server.log 2>&1 &
  fi
  for DPC_ATTEMPT in {1..20}; do
    if dpc_server_ready; then break; fi
    sleep 1
  done
fi
if ! dpc_server_ready; then
  echo "Ollama has not finished starting. Open Ollama from Applications and complete any first-run prompts."
  echo "Leave it running, then open this helper again. If using the standalone server, check logs/ollama_server.log."
  read -r -p "Press Return to close."
  exit 1
fi
echo "Ollama is running. Downloading the model..."
OLLAMA_HOST=127.0.0.1:11434 "$DPC_OLLAMA" pull gemma3:4b
echo "Free local model is ready. In the agent's AI settings choose Free local (Ollama)."
read -r -p "Press Return to close."
