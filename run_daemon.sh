#!/bin/bash
# Daemon launcher — sets up CUDA 12 library paths and starts the mirach package.
#
# CTranslate2 (used by faster-whisper) requires CUDA 12 runtime libraries.
# These are installed via pip as nvidia-cublas-cu12 and nvidia-cudnn-cu12,
# but they live inside the venv's site-packages, not in the system library path.
# This script adds them to LD_LIBRARY_PATH before launching the daemon.

set -euo pipefail

# Self-locate by default: resolve the directory of this script, following symlinks.
# This makes the daemon work no matter where the repo lives. Override with
# MIRACH_BASE_DIR only if you want logs/voices/system_prompt in a different tree.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
BASE_DIR="${MIRACH_BASE_DIR:-$SCRIPT_DIR}"
VENV="$BASE_DIR/venv"

# Auto-detect Python version of the venv (3.12 / 3.13 / etc.)
PYBIN="$VENV/bin/python3"
PYVER="$("$PYBIN" -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
SITE="$VENV/lib/$PYVER/site-packages"

# Add CUDA 12 runtime libraries from the venv to the library search path
export LD_LIBRARY_PATH="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"

# Add the project root to PYTHONPATH so the mirach package is importable
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

# Load mirach.env if present. Precedence: shell > mirach.env > config.py defaults.
# A variable already exported in the calling shell is never overwritten.
if [[ -f "$BASE_DIR/mirach.env" ]]; then
    while IFS='=' read -r key val; do
        [[ "$key" =~ ^[[:space:]]*# || -z "$key" ]] && continue
        key="${key// /}"
        [[ -z "${!key:-}" ]] && export "$key=$val"
    done < "$BASE_DIR/mirach.env"
fi

exec "$PYBIN" -m mirach
