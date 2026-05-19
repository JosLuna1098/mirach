#!/usr/bin/env bash
# Mirach installer — bootstraps everything needed to run the assistant.
#
# Run from the repo root:
#     ./install.sh                       # interactive
#     ./install.sh --yes                 # non-interactive, accept defaults
#     ./install.sh --voice <filename>    # download a specific Piper voice
#     ./install.sh --no-system-deps      # skip the apt/pacman/dnf step
#     ./install.sh --no-opencode         # skip installing OpenCode CLI
#     ./install.sh --no-service          # skip installing the systemd user unit
#     ./install.sh --help                # show this help and exit
#
# Idempotent: re-running it skips steps already done.

set -euo pipefail

# --- Defaults ---
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low.onnx"
DEFAULT_VOICE_NAME="en_US-lessac-low.onnx"
OMARCHY_README_URL="https://raw.githubusercontent.com/robzolkos/omarchy-skill/master/README.md"
OPENCODE_INSTALL_URL="https://opencode.ai/install"

ASSUME_YES=0
INSTALL_SYSTEM_DEPS=1
INSTALL_OPENCODE=1
INSTALL_SERVICE=1
DOWNLOAD_VOICE=1
VOICE_URL="$DEFAULT_VOICE_URL"
VOICE_NAME="$DEFAULT_VOICE_NAME"

# --- Helpers ---
log()  { printf '\033[1;34m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

confirm() {
    local prompt="$1"
    [[ "$ASSUME_YES" == 1 ]] && return 0
    read -r -p "$prompt [Y/n] " ans
    [[ -z "$ans" || "$ans" =~ ^[Yy]$ ]]
}

usage() { sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; }

# --- Arg parsing ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)         ASSUME_YES=1; shift ;;
        --no-system-deps) INSTALL_SYSTEM_DEPS=0; shift ;;
        --no-opencode)    INSTALL_OPENCODE=0; shift ;;
        --no-service)     INSTALL_SERVICE=0; shift ;;
        --no-voice)       DOWNLOAD_VOICE=0; shift ;;
        --voice)          VOICE_NAME="$2"; VOICE_URL=""; shift 2 ;;
        --voice-url)      VOICE_URL="$2"; shift 2 ;;
        --help|-h)        usage; exit 0 ;;
        *) err "Unknown arg: $1"; usage; exit 1 ;;
    esac
done

cd "$REPO_DIR"
log "Mirach install in $REPO_DIR"

# --- 1. System packages ---
detect_pm() {
    if command -v pacman >/dev/null;  then echo pacman
    elif command -v apt-get >/dev/null; then echo apt
    elif command -v dnf >/dev/null;     then echo dnf
    else echo unknown
    fi
}

install_system_deps() {
    local pm; pm="$(detect_pm)"
    if [[ "$pm" == "unknown" ]]; then
        warn "No supported package manager (pacman/apt/dnf). Install manually:"
        warn "  python3, python3-venv, git, curl, alsa-utils, libnotify"
        return 0
    fi

    log "System packages via $pm (requires sudo)"
    case "$pm" in
        pacman)
            sudo pacman -S --needed --noconfirm python git curl alsa-utils libnotify
            ;;
        apt)
            sudo apt-get update
            sudo apt-get install -y python3 python3-venv python3-pip git curl alsa-utils libnotify-bin
            ;;
        dnf)
            sudo dnf install -y python3 python3-pip git curl alsa-utils libnotify
            ;;
    esac
    ok "System packages installed"
}

if [[ "$INSTALL_SYSTEM_DEPS" == 1 ]]; then
    if confirm "Install system packages (python, git, curl, alsa-utils, libnotify)?"; then
        install_system_deps
    else
        warn "Skipping system packages"
    fi
fi

# --- 2. Python virtual env ---
if [[ ! -d "$REPO_DIR/venv" ]]; then
    log "Creating venv"
    python3 -m venv "$REPO_DIR/venv"
    ok "venv created"
else
    ok "venv already exists"
fi

PYBIN="$REPO_DIR/venv/bin/python3"
PIPBIN="$PYBIN -m pip"

log "Upgrading pip"
$PIPBIN install --upgrade pip >/dev/null
ok "pip ready"

log "Installing Python dependencies"
$PIPBIN install -r "$REPO_DIR/requirements.txt"
ok "Dependencies installed"

# --- 3. Piper voice ---
if [[ "$DOWNLOAD_VOICE" == 1 ]]; then
    mkdir -p "$REPO_DIR/voices"
    target="$REPO_DIR/voices/$VOICE_NAME"
    if [[ -f "$target" ]]; then
        ok "Voice $VOICE_NAME already present"
    elif [[ -z "$VOICE_URL" ]]; then
        warn "--voice was set but no --voice-url given; skipping download"
    else
        log "Downloading Piper voice: $VOICE_NAME"
        curl -L --fail -o "$target" "$VOICE_URL"
        curl -L --fail -o "$target.json" "${VOICE_URL}.json"
        ok "Voice downloaded to voices/$VOICE_NAME"
    fi
fi

# --- 4. Omarchy reference (optional, for system prompts that mention it) ---
if [[ ! -f "$REPO_DIR/omarchy.md" ]]; then
    if confirm "Download Omarchy README as omarchy.md (reference for the LLM)?"; then
        log "Fetching $OMARCHY_README_URL"
        curl -L --fail -o "$REPO_DIR/omarchy.md" "$OMARCHY_README_URL"
        ok "omarchy.md downloaded"
    fi
else
    ok "omarchy.md already present (left untouched)"
fi

# --- 5. system_prompt.md ---
if [[ ! -f "$REPO_DIR/system_prompt.md" ]]; then
    if [[ -f "$REPO_DIR/system_prompt.example.md" ]]; then
        log "Copying system_prompt.example.md → system_prompt.md"
        cp "$REPO_DIR/system_prompt.example.md" "$REPO_DIR/system_prompt.md"
        ok "system_prompt.md created — edit it to taste"
    else
        warn "system_prompt.example.md missing"
    fi
else
    ok "system_prompt.md already present (left untouched)"
fi

# --- 6. OpenCode CLI ---
if [[ "$INSTALL_OPENCODE" == 1 ]]; then
    if command -v opencode >/dev/null; then
        ok "OpenCode already installed ($(opencode --version 2>/dev/null || echo ?))"
    elif confirm "Install OpenCode CLI from $OPENCODE_INSTALL_URL?"; then
        log "Installing OpenCode"
        curl -fsSL "$OPENCODE_INSTALL_URL" | bash
        ok "OpenCode installed — run 'opencode auth' to configure"
    else
        warn "Skipping OpenCode — install it manually before starting the daemon"
    fi
fi

# --- 7. systemd user service ---
install_service() {
    local target="$HOME/.config/systemd/user/mirach.service"
    mkdir -p "$(dirname "$target")"
    if [[ -f "$target" ]]; then
        ok "Service already at $target (left untouched)"
    else
        log "Installing mirach.service → $target"
        cp "$REPO_DIR/mirach.service.example" "$target"
        # Patch ExecStart so it points to THIS repo, wherever it lives
        sed -i "s|%h/mirach/run_daemon.sh|$REPO_DIR/run_daemon.sh|" "$target"
        ok "Service installed"
    fi
    systemctl --user daemon-reload
    systemctl --user enable mirach.service >/dev/null
    if systemctl --user is-active --quiet mirach.service; then
        log "Restarting daemon"
        systemctl --user restart mirach.service
    else
        log "Starting daemon"
        systemctl --user start mirach.service
    fi
    ok "Service enabled and running"
}

if [[ "$INSTALL_SERVICE" == 1 ]]; then
    if confirm "Install and enable systemd user service?"; then
        install_service
    else
        warn "Skipping service install"
    fi
fi

# --- Done ---
echo
ok "Install complete."
cat <<EOF

Next steps:
  1. Edit your system prompt:    \$EDITOR $REPO_DIR/system_prompt.md
  2. Bind your hotkey to:        python3 $REPO_DIR/trigger.py
     (Hyprland example: bind = ALT, Z, exec, python3 $REPO_DIR/trigger.py)
  3. Watch logs:                 journalctl --user -u mirach -f
  4. View last conversation:     $REPO_DIR/view_conversation.sh

If you set MIRACH_VOICE to '$VOICE_NAME' or another voice, restart the service.
EOF
