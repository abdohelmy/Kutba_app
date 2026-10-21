#!/usr/bin/env bash
set -euo pipefail
KHUTBA_WORKER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KHUTBA_WHISPER_PYTHON="${KHUTBA_WHISPER_PYTHON:-$HOME/khutba-whisper/bin/python}"
if [[ ! -x "$KHUTBA_WHISPER_PYTHON" ]]; then
  echo "Create ~/khutba-whisper and install requirements-whisper.txt as described in README.md."
  exit 1
fi
# CTranslate2 loads CUDA libraries dynamically. Make the libraries installed in
# this isolated environment visible before Python imports faster-whisper.
KHUTBA_CUDA_LIBS="$("$KHUTBA_WHISPER_PYTHON" -c 'import os, nvidia.cublas, nvidia.cudnn; print(os.path.join(nvidia.cublas.__path__[0], "lib") + ":" + os.path.join(nvidia.cudnn.__path__[0], "lib"))')"
export LD_LIBRARY_PATH="$KHUTBA_CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$KHUTBA_WHISPER_PYTHON" "$KHUTBA_WORKER_DIR/worker.py" --backend whisper "$@"
