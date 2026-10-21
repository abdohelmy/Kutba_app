#!/usr/bin/env bash
set -euo pipefail
KHUTBA_WORKER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KHUTBA_COHERE_PYTHON="${KHUTBA_COHERE_PYTHON:-$HOME/khutba-cohere/bin/python}"
if [[ ! -x "$KHUTBA_COHERE_PYTHON" ]]; then
  echo "Create ~/khutba-cohere and install requirements-cohere.txt; see COHERE-SETUP.md."
  exit 1
fi
# Avoid stale CTranslate2 CUDA paths from the Whisper environment.
unset LD_LIBRARY_PATH
exec "$KHUTBA_COHERE_PYTHON" "$KHUTBA_WORKER_DIR/worker.py" --backend cohere "$@"
