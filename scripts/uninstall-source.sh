#!/usr/bin/env bash
# Removes Gamerdeck installed with scripts/install-source.sh.
#
#   scripts/uninstall-source.sh                 asks whether to also delete your data
#   scripts/uninstall-source.sh --keep-data     removes the app, keeps library and settings
#   scripts/uninstall-source.sh --delete-data   removes everything, without asking
#   scripts/uninstall-source.sh --prefix DIR    if you installed in DIR instead of ~/.local
#
# It removes exactly the files the installation listed, nothing else. The data
# is your library, covers and settings: the folder ~/.local/share/cartridges,
# which is also the one Cartridges uses, and the Gamerdeck settings. Your games
# and the data of Steam, Lutris and the other launchers are never touched.
set -euo pipefail

APP_ID=io.github.jeffersonmk.Gamerdeck
PREFIX="$HOME/.local"
MODE=ask
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/cartridges"

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --keep-data) MODE=keep ;;
        --delete-data) MODE=delete ;;
        --prefix) [ $# -ge 2 ] || die "--prefix needs a folder"; PREFIX="$2"; shift ;;
        -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
        *) die "Unknown option: $1 (use --keep-data, --delete-data or --prefix)" ;;
    esac
    shift
done

[ -d "$PREFIX" ] || die "$PREFIX does not exist. Nothing to remove there."
PREFIX="$(cd "$PREFIX" && pwd)"
MANIFEST="$PREFIX/share/gamerdeck/install-manifest.txt"

if [ ! -f "$MANIFEST" ]; then
    echo "Gamerdeck was not installed from source in $PREFIX (no list of files found). Nothing to do."
    echo "If you installed the Flatpak, use scripts/uninstall-flatpak.sh."
    exit 0
fi

if [ -d "$DATA" ] && [ "$MODE" = ask ]; then
    printf 'Also delete your library and settings (%s and the Gamerdeck settings)?\n' "$DATA"
    printf 'That folder is also the library of Cartridges. [y/N] '
    read -r answer || answer=n
    case "$answer" in [yYsS]*) MODE=delete ;; *) MODE=keep ;; esac
fi

# ------------------------------------------------------------ files, then folders
WORK="$(mktemp -d "${TMPDIR:-/tmp}/gamerdeck-uninstall.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
: > "$WORK/parents"
: > "$WORK/modules"

removed=0
while IFS= read -r path; do
    # Only what is inside the prefix, whatever the list says
    case "$path" in "$PREFIX"/?*) ;; *) continue ;; esac
    if [ -f "$path" ] || [ -L "$path" ]; then
        rm -f -- "$path"
        removed=$((removed + 1))
        # The folders it was in, up to the prefix: emptied below if nothing else is there
        dir="$(dirname "$path")"
        while [ "$dir" != "$PREFIX" ] && [ "${dir#"$PREFIX"/}" != "$dir" ]; do
            echo "$dir" >> "$WORK/parents"
            dir="$(dirname "$dir")"
        done
        case "$path" in
            */site-packages/cartridges/*) echo "${path%%/site-packages/cartridges/*}/site-packages/cartridges" >> "$WORK/modules" ;;
        esac
    fi
done < "$MANIFEST"

# Python leaves its caches (__pycache__) in the folder of the app: they are not in the list
sort -u "$WORK/modules" | while IFS= read -r module; do
    [ -d "$module" ] && find "$module" -type d -name __pycache__ -prune -exec rm -r -- {} +
done

# The caches the installation updated
SCHEMAS="$PREFIX/share/glib-2.0/schemas"
if [ -d "$SCHEMAS" ]; then
    if ls "$SCHEMAS"/*.gschema.xml >/dev/null 2>&1; then
        glib-compile-schemas "$SCHEMAS" 2>/dev/null || true
    else
        rm -f -- "$SCHEMAS/gschemas.compiled"
        rmdir -- "$SCHEMAS" 2>/dev/null || true
    fi
fi
if [ -d "$PREFIX/share/icons/hicolor" ] && command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -q -t -f "$PREFIX/share/icons/hicolor" 2>/dev/null || true
fi
[ -d "$PREFIX/share/applications" ] && command -v update-desktop-database >/dev/null &&
    update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true

# If nothing else lives in those folders, the caches go too (and then the folders)
APPS="$PREFIX/share/applications"
if [ -f "$APPS/mimeinfo.cache" ] && [ -z "$(find "$APPS" -type f ! -name mimeinfo.cache -print -quit)" ]; then
    rm -f -- "$APPS/mimeinfo.cache"
fi
ICONS="$PREFIX/share/icons/hicolor"
if [ -f "$ICONS/icon-theme.cache" ] && [ -z "$(find "$ICONS" -type f ! -name icon-theme.cache -print -quit)" ]; then
    rm -f -- "$ICONS/icon-theme.cache"
fi

# Empty folders, the deepest first (rmdir leaves alone the ones that still have something)
sort -u "$WORK/parents" | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2- |
    while IFS= read -r dir; do rmdir -- "$dir" 2>/dev/null || true; done
rmdir -- "$PREFIX/share/gamerdeck" 2>/dev/null || true

# ------------------------------------------------------------------------- data
if [ "$MODE" = delete ]; then
    if [ -d "$DATA" ]; then
        case "$DATA" in /?*/?*) rm -r -- "$DATA" ;; *) die "Refusing to delete $DATA" ;; esac
    fi
    command -v dconf >/dev/null && dconf reset -f "/${APP_ID//./\/}/" 2>/dev/null || true
fi

echo
echo "Gamerdeck was removed ($removed files)."
if [ "$MODE" = delete ]; then
    echo "Your library and settings were deleted."
else
    echo "Your library is kept in $DATA (installing again brings it back; to delete it: $0 --delete-data)."
fi
