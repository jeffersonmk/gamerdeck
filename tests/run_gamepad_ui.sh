#!/bin/sh
# Run the controller UI driver without touching your real display.
# Usage: tests/run_gamepad_ui.sh [shots-dir]   (needs an installed build, see tests/support.py)
#
# With KWin installed, the app runs on a virtual Wayland session (kwin_wayland
# --virtual): the same GTK backend and renderer as on a real desktop, no
# window on your screen and no input grabs. Otherwise it falls back to GTK's
# Broadway backend, which only lays out on time while a browser is connected
# (set GAMERDECK_BROWSER to a Chromium/Chrome binary, it runs headless) and
# crashes on some icons: use it only when KWin is not available.
cd "$(dirname "$0")/.." || exit 1
[ -n "$1" ] && export GAMEPAD_UI_SHOTS="$1"

if command -v kwin_wayland >/dev/null 2>&1 && command -v dbus-run-session >/dev/null 2>&1; then
    RUNTIME=$(mktemp -d)
    chmod 700 "$RUNTIME"
    export XDG_RUNTIME_DIR="$RUNTIME"
    env -u WAYLAND_DISPLAY -u DISPLAY dbus-run-session -- sh -c '
        kwin_wayland --virtual --no-lockscreen --socket gamepad-ui \
            --width 1280 --height 900 >"$XDG_RUNTIME_DIR/kwin.log" 2>&1 &
        KWIN=$!
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            [ -S "$XDG_RUNTIME_DIR/gamepad-ui" ] && break
            sleep 0.5
        done
        env -u DISPLAY GDK_BACKEND=wayland WAYLAND_DISPLAY=gamepad-ui GTK_A11Y=none \
            PATH=/usr/local/bin:/usr/bin:/bin /usr/bin/python3 -m ${GAMERDECK_UI_MODULE:-tests.gamepad_ui}
        STATUS=$?
        kill "$KWIN"
        exit "$STATUS"
    '
    STATUS=$?
    rm -rf "$RUNTIME"
    exit "$STATUS"
fi

N="${GAMEPAD_UI_DISPLAY:-31}"
gtk4-broadwayd ":$N" >/dev/null 2>&1 &
BROADWAY=$!
sleep 1
BROWSER_PID=
if [ -n "$GAMERDECK_BROWSER" ]; then
    PROFILE=$(mktemp -d)
    "$GAMERDECK_BROWSER" --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
        --window-size=1600,1000 --user-data-dir="$PROFILE" \
        "http://127.0.0.1:$((8080 + N))/" >/dev/null 2>&1 &
    BROWSER_PID=$!
    sleep 2
fi
env -u WAYLAND_DISPLAY -u DISPLAY GDK_BACKEND=broadway BROADWAY_DISPLAY=":$N" \
    GTK_A11Y=none PATH=/usr/local/bin:/usr/bin:/bin \
    /usr/bin/python3 -m ${GAMERDECK_UI_MODULE:-tests.gamepad_ui}
STATUS=$?
[ -n "$BROWSER_PID" ] && kill "$BROWSER_PID"
kill "$BROADWAY"
exit "$STATUS"
