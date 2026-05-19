#!/usr/bin/env bash
# Open the most recent assistant conversation in a terminal with markdown highlighting.
# Intended for a keyboard shortcut (e.g. Alt+Shift+Z) or manual invocation.

set -euo pipefail

BASE_DIR="${MIRACH_BASE_DIR:-$HOME/mirach}"
CONV_DIR="$BASE_DIR/logs/conversations"
LATEST="$CONV_DIR/latest.md"

if [[ ! -e "$LATEST" ]]; then
    notify-send -i dialog-information "🤖 Mirach" "No conversations saved yet."
    exit 0
fi

# Pick a viewer: bat > glow > less
if command -v bat >/dev/null 2>&1; then
    VIEWER=(bat --paging=always --style=plain --language=markdown)
elif command -v glow >/dev/null 2>&1; then
    VIEWER=(glow -p)
else
    VIEWER=(less -R)
fi

# Launch in a terminal. Prefer uwsm-app + alacritty (Omarchy default); fall back to xdg.
if command -v uwsm-app >/dev/null 2>&1 && command -v alacritty >/dev/null 2>&1; then
    exec uwsm-app -- alacritty -e bash -c "${VIEWER[*]} '$LATEST'; echo; read -n1 -s -p 'Press any key to close...'"
elif command -v alacritty >/dev/null 2>&1; then
    exec alacritty -e bash -c "${VIEWER[*]} '$LATEST'; echo; read -n1 -s -p 'Press any key to close...'"
else
    # Last resort: open the file in the default markdown handler
    exec xdg-open "$LATEST"
fi
