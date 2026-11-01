#!/usr/bin/env bash
# Builds Gamerdeck.flatpak: one file that installs the app on any computer with
# Flatpak (see scripts/install-flatpak.sh).
#
#   scripts/build-flatpak.sh                 creates Gamerdeck.flatpak in the main folder
#   scripts/build-flatpak.sh /path/to.flatpak   creates it somewhere else
#
# The first build downloads the GNOME SDK (about 1 GB, once) and takes a few
# minutes. The next ones are much faster.
set -euo pipefail

APP_ID=io.github.jeffersonmk.Gamerdeck
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/Gamerdeck.flatpak}"
MANIFEST="$ROOT/build-aux/flatpak/$APP_ID.json"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v flatpak >/dev/null || die "Flatpak is not installed. See https://flatpak.org/setup/"
flatpak remotes | awk '{print $1}' | grep -qx flathub ||
    die "The Flathub repository is not set up. Run: flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"

# flatpak-builder: installed on the system, or the Flatpak version of it
if command -v flatpak-builder >/dev/null; then
    BUILDER=(flatpak-builder)
elif flatpak info org.flatpak.Builder >/dev/null 2>&1; then
    BUILDER=(flatpak run org.flatpak.Builder)
else
    die "flatpak-builder is missing. Install it with: flatpak install --user flathub org.flatpak.Builder"
fi

# Leftover Python caches of the source folder must not end up in the package
find "$ROOT/cartridges" "$ROOT/tests" "$ROOT/search-provider" -name __pycache__ -type d -prune -exec rm -r {} + 2>/dev/null || true

say "Building $APP_ID (the first time takes a few minutes)"
"${BUILDER[@]}" --user --install-deps-from=flathub --force-clean --disable-rofiles-fuse \
    --state-dir="$ROOT/.flatpak-builder" --repo="$ROOT/.flatpak-repo" \
    "$ROOT/.flatpak-build" "$MANIFEST"

say "Creating $OUT"
flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    "$ROOT/.flatpak-repo" "$OUT" "$APP_ID"

say "Done: $OUT ($(du -h "$OUT" | cut -f1))"
echo "To install it:  $ROOT/scripts/install-flatpak.sh \"$OUT\""
