#!/bin/bash
# Daemon launcher — sets up CUDA 12 libs and starts the mirach package.
set -euo pipefail

BASE_DIR="${MIRACH_BASE_DIR:-$HOME/mirach}"
VENV="$BASE_DIR/venv"

# Auto-detect python version of the venv (3.12 / 3.13 / etc.)
PYBIN="$VENV/bin/python3"
PYVER="$("$PYBIN" -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')"
SITE="$VENV/lib/$PYVER/site-packages"

# CTranslate2 (faster-whisper) needs CUDA 12 — libs come via pip, not from the system
export LD_LIBRARY_PATH="$SITE/nvidia/cublas/lib:$SITE/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"

# The mirach/ package lives next to this script; add it to PYTHONPATH instead of installing
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

exec "$PYBIN" -m mirach
