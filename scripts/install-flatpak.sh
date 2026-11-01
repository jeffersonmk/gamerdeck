#!/usr/bin/env bash
# Installs (or updates) Gamerdeck from a Gamerdeck.flatpak file, for your user only.
# The app appears in the applications menu, with its icon.
#
#   scripts/install-flatpak.sh                       uses ./Gamerdeck.flatpak
#   scripts/install-flatpak.sh /path/to/Gamerdeck.flatpak
#
# Your library and settings are kept when you update.
set -euo pipefail

APP_ID=io.github.jeffersonmk.Gamerdeck
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v flatpak >/dev/null || die "Flatpak is not installed. See https://flatpak.org/setup/"

BUNDLE="${1:-}"
if [ -z "$BUNDLE" ]; then
    for candidate in "$PWD/Gamerdeck.flatpak" "$ROOT/Gamerdeck.flatpak"; do
        if [ -f "$candidate" ]; then BUNDLE="$candidate"; break; fi
    done
fi
[ -n "$BUNDLE" ] && [ -f "$BUNDLE" ] ||
    die "Gamerdeck.flatpak not found. Download it, or build it with scripts/build-flatpak.sh, or give its path: $0 /path/to/Gamerdeck.flatpak"

if flatpak info --user "$APP_ID" >/dev/null 2>&1; then
    echo "Gamerdeck is already installed: updating it (your library and settings stay)."
fi

LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT
if ! flatpak install --user -y "$BUNDLE" 2>&1 | tee "$LOG"; then
    # Installing the very same build again is not a problem
    if grep -q "already installed" "$LOG"; then
        echo
        echo "This exact version of Gamerdeck is already installed. Nothing to do."
        exit 0
    fi
    exit 1
fi

echo
echo "Gamerdeck is installed. Open it from the applications menu, or run:"
echo "    flatpak run $APP_ID"
