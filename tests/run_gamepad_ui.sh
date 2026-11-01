#!/bin/sh
# Run the controller UI driver inside a private Broadway display.
# Usage: tests/run_gamepad_ui.sh [shots-dir]   (needs an installed build, see tests/support.py)
#
# Broadway only lays out and scrolls on time while a browser is connected, so
# set GAMEDECK_BROWSER to a Chromium/Chrome binary (it runs headless). Without
# it the grid is laid out lazily and the scrolling checks can fail.
cd "$(dirname "$0")/.." || exit 1
N="${GAMEPAD_UI_DISPLAY:-31}"
gtk4-broadwayd ":$N" >/dev/null 2>&1 &
BROADWAY=$!
sleep 1
BROWSER_PID=
if [ -n "$GAMEDECK_BROWSER" ]; then
    PROFILE=$(mktemp -d)
    "$GAMEDECK_BROWSER" --headless --no-sandbox --disable-gpu --disable-dev-shm-usage --window-size=1600,1000 \
        --user-data-dir="$PROFILE" "http://127.0.0.1:$((8080 + N))/" \
        >/dev/null 2>&1 &
    BROWSER_PID=$!
    sleep 2
fi
[ -n "$1" ] && export GAMEPAD_UI_SHOTS="$1"
env -u WAYLAND_DISPLAY -u DISPLAY GDK_BACKEND=broadway BROADWAY_DISPLAY=":$N" \
    GTK_A11Y=none PATH=/usr/local/bin:/usr/bin:/bin \
    /usr/bin/python3 -m tests.gamepad_ui
STATUS=$?
[ -n "$BROWSER_PID" ] && kill "$BROWSER_PID"
kill "$BROADWAY"
exit "$STATUS"
