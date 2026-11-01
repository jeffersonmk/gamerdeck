#!/usr/bin/env bash
# Removes Gamerdeck (the Flatpak) from your user.
#
#   scripts/uninstall-flatpak.sh                 asks whether to also delete your data
#   scripts/uninstall-flatpak.sh --keep-data     removes the app, keeps library and settings
#   scripts/uninstall-flatpak.sh --delete-data   removes everything, without asking
#
# The data is what Gamerdeck saved for itself: your library, covers, settings
# and logs, in ~/.var/app/io.github.jeffersonmk.Gamerdeck. Your games and the
# data of Steam, Lutris and the other launchers are never touched.
set -euo pipefail

APP_ID=io.github.jeffersonmk.Gamerdeck
DATA="$HOME/.var/app/$APP_ID"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

MODE=ask
case "${1:-}" in
    "") ;;
    --keep-data) MODE=keep ;;
    --delete-data) MODE=delete ;;
    -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
    *) die "Unknown option: $1 (use --keep-data or --delete-data)" ;;
esac

command -v flatpak >/dev/null || die "Flatpak is not installed."

installed=no
if flatpak info --user "$APP_ID" >/dev/null 2>&1; then
    installed=yes
elif flatpak info --system "$APP_ID" >/dev/null 2>&1; then
    die "Gamerdeck is installed for the whole system. Remove it with: sudo flatpak uninstall $APP_ID"
fi

if [ "$installed" = no ] && [ ! -d "$DATA" ]; then
    echo "Gamerdeck is not installed and has no data here. Nothing to do."
    exit 0
fi

if [ -d "$DATA" ] && [ "$MODE" = ask ]; then
    printf 'Also delete your Gamerdeck library and settings (%s)? [y/N] ' "$DATA"
    read -r answer || answer=n
    case "$answer" in [yYsS]*) MODE=delete ;; *) MODE=keep ;; esac
fi

if [ "$installed" = yes ]; then
    if [ "$MODE" = delete ]; then
        flatpak uninstall --user -y --delete-data "$APP_ID"
    else
        flatpak uninstall --user -y "$APP_ID"
    fi
fi

# --delete-data only works while the app is installed: finish the job if it was already gone
if [ "$MODE" = delete ] && [ -d "$DATA" ]; then
    case "$DATA" in "$HOME"/.var/app/?*) rm -r -- "$DATA" ;; *) die "Refusing to delete $DATA" ;; esac
fi

echo
if [ "$MODE" = delete ]; then
    echo "Gamerdeck and its data were removed."
else
    echo "Gamerdeck was removed. Your library and settings are kept in $DATA"
    echo "(installing it again brings them back; to delete them: $0 --delete-data)"
fi
echo "To free the space of runtimes nobody uses anymore: flatpak uninstall --unused"
