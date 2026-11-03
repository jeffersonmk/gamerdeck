#!/usr/bin/env bash
# Updates Gamerdeck installed with scripts/install-source.sh.
#
#   scripts/update.sh                 downloads the newest version and installs it
#   scripts/update.sh --check         only tells whether there is a newer version
#                                     (exit code 0: up to date, 10: update available)
#   scripts/update.sh --reinstall     installs again even if nothing new was downloaded
#   scripts/update.sh --prefix DIR    if you installed in DIR instead of ~/.local
#   scripts/update.sh --force         passed on to install-source.sh
#
# It runs "git pull" in the folder you cloned Gamerdeck to, then
# scripts/install-source.sh. Your library and settings are not touched.
# The app runs this same script from Preferences > Updates.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK=no
REINSTALL=no
INSTALL_ARGS=()

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --check) CHECK=yes ;;
        --reinstall) REINSTALL=yes ;;
        --force) INSTALL_ARGS+=("$1") ;;
        --prefix) [ $# -ge 2 ] || die "--prefix needs a folder"; INSTALL_ARGS+=("$1" "$2"); shift ;;
        -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
        *) die "Unknown option: $1 (see --help)" ;;
    esac
    shift
done

command -v git >/dev/null || die "git is not installed (Arch Linux: sudo pacman -S git)."
[ -d "$ROOT/.git" ] || die "$ROOT is not a git clone, so there is nothing to download. Clone Gamerdeck again with git, or install from a newer copy of the folder."
cd "$ROOT"

version() { sed -n "s/^[[:space:]]*version:[[:space:]]*'\([^']*\)'.*/\1/p" meson.build | head -n 1; }

say "Looking for a new version"
git fetch --quiet || die "Could not reach the repository. Check your internet connection."
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[ -n "$UPSTREAM" ] || die "This copy of Gamerdeck does not follow a branch of GitHub (no upstream). Run: git branch --set-upstream-to=origin/main"
BEHIND="$(git rev-list --count "HEAD..$UPSTREAM")"

if [ "$CHECK" = yes ]; then
    if [ "$BEHIND" -gt 0 ]; then
        echo "A new version is available ($BEHIND new changes)."
        exit 10
    fi
    echo "Gamerdeck is up to date (version $(version))."
    exit 0
fi

if [ "$BEHIND" -gt 0 ]; then
    say "Downloading $BEHIND new changes"
    git pull --ff-only --quiet || die "Could not apply the new version. You changed files of the folder $ROOT and they conflict: save them (git stash) and run this script again."
elif [ "$REINSTALL" = no ]; then
    echo "Gamerdeck is already up to date (version $(version)). Use --reinstall to install it again."
    exit 0
fi

# A bash that is not the first python3 of the PATH (a virtual environment, for
# instance) must not become the Python of the installed app
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

"$ROOT/scripts/install-source.sh" "${INSTALL_ARGS[@]}"
say "Updated to version $(version)"
