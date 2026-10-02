#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LD_LIBRARY_PATH=/usr/lib/arm-linux-gnueabihf:/lib/arm-linux-gnueabihf:/usr/lib:/lib
export QT_PLUGIN_PATH=/usr/lib/arm-linux-gnueabihf/qt5/plugins
export QML2_IMPORT_PATH=/usr/lib/arm-linux-gnueabihf/qt5/qml
export QT_QUICK_BACKEND=software
export QT_QPA_PLATFORM=wayland
[ "$1" != app ] && export DEVKIT_LEGACY_DISPLAY=1
export QT_WAYLAND_SHELL_INTEGRATION=wl-shell
export QT_WAYLAND_DISABLE_WINDOWDECORATION=1
export QT_QPA_FONTDIR=/usr/share/fonts
export XDG_RUNTIME_DIR=/dev/x2dii-runtime
export XDG_CACHE_HOME=/dev/x2dii-cache
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/dev/socket/dbus
export DBUS_SESSION_BUS_ADDRESS="$DBUS_SYSTEM_BUS_ADDRESS"
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CACHE_HOME" /run/dbus /data/config
chmod 700 "$XDG_RUNTIME_DIR"
if [ ! -s /etc/machine-id ]; then dbus-uuidgen > /etc/machine-id; fi
fast_input=
fast_frames=
for name in /sys/class/virtio-ports/*/name; do
    [ -f "$name" ] || continue
    device=${name%/name}
    case "$(cat "$name")" in
        x2dii.input) fast_input=/dev/${device##*/} ;;
        x2dii.frames) fast_frames=/dev/${device##*/} ;;
    esac
done
/devkit/mini_compositor /dev/block/vdf "$fast_input" "$fast_frames" &
compositor=$!
dbus-daemon --config-file=/devkit/camera/dbus-local.conf --nofork --nosyslog --nopidfile &
bus=$!
sleep 1
/devkit/mock_services &
mock=$!
sleep 1
if [ "$1" = app ]; then
    export DEVKIT_WIDTH=640 DEVKIT_HEIGHT=480
    app_entry=${2:-app/hello}
    case "$app_entry" in
        /*|*..*|*[!a-zA-Z0-9_./+-]*) echo X2DII_UI_FAILED; exit 1 ;;
    esac
    if [ ! -f "/devkit/$app_entry" ]; then echo X2DII_UI_FAILED; exit 1; fi
    app_lib=${3:-}
    if [ -n "$app_lib" ]; then
        case "$app_lib" in
            apps/*/*/lib) ;;
            *) echo X2DII_UI_FAILED; exit 1 ;;
        esac
        case "$app_entry" in
            "${app_lib%/lib}"/*) ;;
            *) echo X2DII_UI_FAILED; exit 1 ;;
        esac
        app_root=${app_lib%/lib}
        (cd "/devkit/$app_root" &&
            export LD_LIBRARY_PATH="/devkit/$app_lib:$LD_LIBRARY_PATH" &&
            exec "/devkit/$app_entry") &
    else
        "/devkit/$app_entry" &
    fi
else
    cp /devkit/camera/victory-gui-software /usr/bin/victory-gui-software
    chmod 755 /usr/bin/victory-gui-software
    /usr/bin/victory-gui-software -platform wayland --fullscreen --wedge &
fi
gui=$!
sleep 15
if ! kill -0 "$gui"; then
    wait "$gui"; echo LEGACY_UI_RC=$?
    echo X2DII_UI_FAILED
    exit 1
fi
if [ "$1" != app ]; then
    echo 'key 59 1' > /dev/x2dii-input
    sleep 0.1
    echo 'key 59 0' > /dev/x2dii-input
    sleep 3
fi
echo X2DII_UI_SESSION_READY
wait "$gui"
echo X2DII_UI_EXITED
kill "$compositor" "$bus" "$mock"
