#!/usr/bin/env bash
# bootstrap.sh — Mirach one-liner installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/JosLuna1098/mirach/master/bootstrap.sh | bash
#   bash bootstrap.sh [--yes|-y] [--help|-h]
#
# Environment:
#   MIRACH_DIR   Clone destination (default: ~/mirach)
#
# What it does:
#   1. Installs system packages (python3, git, portaudio, etc.) via sudo
#   2. Clones the repo to $MIRACH_DIR (or git-pulls if it already exists)
#   3. Launches the interactive install wizard (python3 install.py)

set -euo pipefail

REPO_URL="https://github.com/JosLuna1098/mirach"
MIRACH_DIR="${MIRACH_DIR:-$HOME/mirach}"
ASSUME_YES=0

# ── colour helpers ────────────────────────────────────────────────────────────
log()  { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
bootstrap.sh — Mirach one-liner installer

  curl -fsSL https://raw.githubusercontent.com/JosLuna1098/mirach/master/bootstrap.sh | bash

Options:
  --yes, -y    Non-interactive: accept all install.py defaults
  --help, -h   Show this help and exit

Environment:
  MIRACH_DIR   Clone destination (default: ~/mirach)
EOF
}

# ── arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)  ASSUME_YES=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) err "Unknown argument: $1. Run with --help for usage." ;;
    esac
done

# ── root guard ────────────────────────────────────────────────────────────────
# The venv and systemctl --user must run as a normal user; sudo is used only
# in the system-packages step below.
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    err "Do not run this script as root.
It uses sudo only for system packages — re-run as your normal user:
  bash bootstrap.sh"
fi

# ── local-checkout guard ──────────────────────────────────────────────────────
# bootstrap.sh is meant for the curl one-liner on a fresh machine. If someone
# runs it from inside an already-cloned checkout (e.g. `bash bootstrap.sh`),
# don't clone a second copy — point them at the wizard and bail.
# (Via curl|bash, BASH_SOURCE[0] is "bash", so this never triggers.)
SCRIPT_PATH="${BASH_SOURCE[0]:-}"
if [[ "$(basename -- "$SCRIPT_PATH" 2>/dev/null || true)" == "bootstrap.sh" && -f "$SCRIPT_PATH" ]]; then
    SCRIPT_DIR="$(cd "$(dirname -- "$SCRIPT_PATH")" && pwd)"
    if [[ -d "$SCRIPT_DIR/.git" && -f "$SCRIPT_DIR/install.py" ]]; then
        warn "You're running bootstrap.sh from inside an existing Mirach checkout:"
        warn "  $SCRIPT_DIR"
        warn "bootstrap.sh is only for the fresh curl one-liner install."
        warn "You already have the repo — run the wizard directly instead:"
        printf '\n    cd %s && python3 install.py\n\n' "$SCRIPT_DIR"
        exit 1
    fi
fi

# ── 1. system packages ────────────────────────────────────────────────────────
detect_pm() {
    if   command -v pacman  >/dev/null 2>&1; then echo pacman
    elif command -v apt-get >/dev/null 2>&1; then echo apt
    elif command -v dnf     >/dev/null 2>&1; then echo dnf
    else echo unknown
    fi
}

install_system_deps() {
    local pm; pm="$(detect_pm)"
    case "$pm" in
        pacman)
            log "Installing system packages via pacman (requires sudo)"
            sudo pacman -S --needed --noconfirm \
                python git curl alsa-utils libnotify portaudio
            ;;
        apt)
            log "Installing system packages via apt (requires sudo)"
            sudo apt-get update -qq
            sudo apt-get install -y \
                python3 python3-venv python3-pip \
                git curl alsa-utils libnotify-bin portaudio19-dev
            ;;
        dnf)
            log "Installing system packages via dnf (requires sudo)"
            sudo dnf install -y \
                python3 python3-pip \
                git curl alsa-utils libnotify portaudio-devel
            ;;
        unknown)
            warn "No supported package manager found (pacman / apt / dnf)."
            warn "Please install these packages manually before continuing:"
            warn "  python3  python3-venv  git  curl  alsa-utils  libnotify  portaudio"
            ;;
    esac
    ok "System packages ready"
}

install_system_deps

# ── 2. clone / update repo ────────────────────────────────────────────────────
if [[ -e "$MIRACH_DIR" ]]; then
    if [[ -d "$MIRACH_DIR/.git" ]]; then
        ok "You already have Mirach installed at $MIRACH_DIR"
        log "Updating to the latest version (git pull --ff-only)"
        git -C "$MIRACH_DIR" pull --ff-only
        ok "Repo updated"
    else
        err "$MIRACH_DIR exists but is not a git repository.
Remove or rename it, then re-run."
    fi
else
    log "Cloning Mirach to $MIRACH_DIR"
    git clone "$REPO_URL" "$MIRACH_DIR"
    ok "Repo cloned"
fi

# ── 3. launch wizard ──────────────────────────────────────────────────────────
log "Launching install wizard"

if [[ "$ASSUME_YES" -eq 1 ]]; then
    # Explicit non-interactive mode
    python3 "$MIRACH_DIR/install.py" --yes
elif { </dev/tty; } 2>/dev/null; then
    # stdin is the curl pipe; redirect the wizard's input() calls from the real
    # terminal so the user can answer prompts interactively.
    python3 "$MIRACH_DIR/install.py" < /dev/tty
else
    warn "No interactive terminal available — running non-interactively."
    python3 "$MIRACH_DIR/install.py" --yes
fi
