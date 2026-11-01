#!/usr/bin/env bash
# Installs Gamerdeck from the source code, for your user: no Flatpak, no sudo.
#
#   scripts/install-source.sh                 installs (or updates) in ~/.local
#   scripts/install-source.sh --force         installs even if another "cartridges" is installed
#   scripts/install-source.sh --prefix DIR    installs in DIR instead of ~/.local (advanced)
#
# It builds the app, copies it to the prefix and writes the list of what it
# installed, so scripts/uninstall-source.sh can remove it completely (Meson has
# no "uninstall" of its own). Running it again updates the app.
set -euo pipefail

APP_ID=io.github.jeffersonmk.Gamerdeck
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/.build-source"
PREFIX="$HOME/.local"
FORCE=no

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --force) FORCE=yes ;;
        --prefix) [ $# -ge 2 ] || die "--prefix needs a folder"; PREFIX="$2"; shift ;;
        -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
        *) die "Unknown option: $1 (see --help)" ;;
    esac
    shift
done

PREFIX="$(mkdir -p "$PREFIX" && cd "$PREFIX" && pwd)"
case "$PREFIX" in *[[:space:]]*) die "The folder \"$PREFIX\" has a space in its name, which the application menu does not accept. Choose another with --prefix." ;; esac

MANIFEST="$PREFIX/share/gamerdeck/install-manifest.txt"

# ---------------------------------------------------------------- requirements
say "Checking what the build needs"

missing=()
for tool in meson ninja python3; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
    die "Missing: ${missing[*]}. On Arch Linux: sudo pacman -S meson blueprint-compiler gettext desktop-file-utils. The README lists the other requirements."
fi

# blueprint-compiler: installed, or downloaded by Meson (which needs git and the network)
if ! command -v blueprint-compiler >/dev/null && [ ! -d "$ROOT/subprojects/blueprint-compiler" ] && ! command -v git >/dev/null; then
    die "blueprint-compiler is missing. Install it (Arch Linux: sudo pacman -S blueprint-compiler) or install git, so Meson can download it."
fi

python3 - <<'PY' || die "The Python of this system cannot run Gamerdeck (see above). The README lists the requirements."
import sys

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk
except (ImportError, ValueError) as error:
    sys.exit(f"GTK 4, libadwaita or PyGObject is missing: {error}")

if (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 15):
    sys.exit("GTK 4.15 or newer is needed, this system has %d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version()))
if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 6):
    sys.exit("libadwaita 1.6 or newer is needed, this system has %d.%d" % (Adw.get_major_version(), Adw.get_minor_version()))

for module, package in (("yaml", "PyYAML"), ("requests", "requests"), ("PIL", "Pillow")):
    try:
        __import__(module)
    except ImportError:
        sys.exit(f"The Python module {package} is missing")
PY

# Gamerdeck keeps the command "cartridges" and the Python package "cartridges"
# (so the library and the upstream merges stay compatible). Installed in the
# user folders, they would take the place of the ones of another Cartridges.
other="$(command -v cartridges || true)"
if [ -n "$other" ] && [ "$other" != "$PREFIX/bin/cartridges" ] && [ "$FORCE" = no ]; then
    die "Cartridges is already installed ($other) and would stop working: Gamerdeck replaces its command and its Python files. Remove it first, or use the Flatpak of Gamerdeck, or run this script with --force if you really want both."
fi

# ----------------------------------------------------------------------- build
say "Building"
SETUP=(meson setup "$BUILD" "$ROOT" --prefix "$PREFIX" -Dprofile=release -Dapp_id="$APP_ID")
[ -f "$BUILD/meson-private/coredata.dat" ] && SETUP+=(--reconfigure)
LOG="$(mktemp "${TMPDIR:-/tmp}/gamerdeck-install.XXXXXX")"
trap 'rm -f "$LOG"' EXIT
"${SETUP[@]}" >"$LOG" 2>&1 || { tail -n 30 "$LOG" >&2; die "Meson could not set up the build (the end of its output is above)."; }

say "Installing in $PREFIX"
meson install -C "$BUILD" >"$LOG" 2>&1 || { tail -n 30 "$LOG" >&2; die "The installation failed (the end of the output is above)."; }

# --------------------------------------------------------------- what was installed
NEW_LIST="$(mktemp "${TMPDIR:-/tmp}/gamerdeck-list.XXXXXX")"
trap 'rm -f "$LOG" "$NEW_LIST"' EXIT
grep '^/' "$BUILD/meson-logs/install-log.txt" > "$NEW_LIST" || die "Meson did not list what it installed."

# A command with the name of the app, for the terminal
ln -sf cartridges "$PREFIX/bin/gamerdeck"
echo "$PREFIX/bin/gamerdeck" >> "$NEW_LIST"

# The application menu starts the app with the command alone: give it the whole path,
# because ~/.local/bin is not always in the PATH of the desktop session
DESKTOP="$PREFIX/share/applications/$APP_ID.desktop"
[ -f "$DESKTOP" ] || die "Meson did not install $DESKTOP"
sed -i "s|^Exec=cartridges\$|Exec=$PREFIX/bin/cartridges|" "$DESKTOP"
grep -q "^Exec=$PREFIX/bin/cartridges\$" "$DESKTOP" || die "Could not set the command of the application menu entry."

# An update: what the previous version installed and this one does not is removed
if [ -f "$MANIFEST" ]; then
    while IFS= read -r path; do
        case "$path" in "$PREFIX"/?*) ;; *) continue ;; esac
        if [ -f "$path" ] || [ -L "$path" ]; then rm -f -- "$path"; fi
    done < <(comm -23 <(sort -u "$MANIFEST") <(sort -u "$NEW_LIST"))
fi

mkdir -p "$(dirname "$MANIFEST")"
cp "$NEW_LIST" "$MANIFEST"
echo "$MANIFEST" >> "$MANIFEST"

# ---------------------------------------------------------------------- the end
say "Done"
echo "Gamerdeck is installed in $PREFIX."
echo "It appears in the applications menu (if not, log out and in again), or start it with:"
echo "    $PREFIX/bin/gamerdeck"
case ":$PATH:" in
    *":$PREFIX/bin:"*) ;;
    *) echo
       echo "The command \"gamerdeck\" only works in a terminal after $PREFIX/bin is in your PATH."
       echo "(bash/zsh: add it to ~/.profile.  fish: fish_add_path $PREFIX/bin)" ;;
esac
if [ -d "$HOME/.local/share/flatpak" ] && command -v flatpak >/dev/null && flatpak info --user "$APP_ID" >/dev/null 2>&1; then
    echo
    echo "Note: the Flatpak of Gamerdeck is installed too. They have the same id, so the menu shows only one of them."
fi
echo
echo "Your library is the same folder Cartridges uses, ${XDG_DATA_HOME:-$HOME/.local/share}/cartridges. The settings start empty."
echo "To update: git pull, then run this script again. To remove: scripts/uninstall-source.sh"
