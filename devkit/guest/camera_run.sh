#!/system/bin/sh
camera_lib=/mnt/x2dii/camera/lib
unset LD_LIBRARY_PATH
export XDG_RUNTIME_DIR=/dev/x2dii-runtime
export XDG_CACHE_HOME=/dev/x2dii-cache
export QT_QUICK_BACKEND=software
export QML_DISABLE_DISK_CACHE=1
export QT_LOGGING_RULES='qt.qpa.*=false'
export XKB_CONFIG_ROOT=/mnt/x2dii/camera/xkb
export QT_WAYLAND_SHELL_INTEGRATION=wl-shell
export QT_WAYLAND_DISABLE_WINDOWDECORATION=1
export QT_QPA_FONTDIR=/mnt/x2dii/camera/fonts
export DBUS_SYSTEM_BUS_ADDRESS=unix:path=/dev/socket/dbus
export DBUS_SESSION_BUS_ADDRESS="$DBUS_SYSTEM_BUS_ADDRESS"
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CACHE_HOME"
chmod 700 "$XDG_RUNTIME_DIR"
mount -o remount,rw /
if [ -f /mnt/x2dii/camera/linker ]; then
    cp /mnt/x2dii/camera/linker /system/bin/linker
    chmod 755 /system/bin/linker
    mkdir -p /system/lib
    mount -o bind /mnt/x2dii/camera/lib /system/lib
fi
cp /mnt/x2dii/camera/etc/VERSION /system/etc/VERSION
cp /mnt/x2dii/camera/etc/dji.json /system/etc/dji.json
setprop persist.hbl.first_time_guide_completed 1
fast_input=
fast_frames=
for port_name in /sys/class/virtio-ports/*/name; do
    [ -f "$port_name" ] || continue
    if [ "$(cat "$port_name")" = x2dii.input ]; then
        port_device=${port_name%/name}
        fast_input=/dev/${port_device##*/}
    fi
    if [ "$(cat "$port_name")" = x2dii.frames ]; then
        port_device=${port_name%/name}
        fast_frames=/dev/${port_device##*/}
    fi
done
LD_LIBRARY_PATH=$camera_lib /mnt/x2dii/mini_compositor /dev/block/vdf $fast_input $fast_frames &
compositor_pid=$!
LD_LIBRARY_PATH=$camera_lib /mnt/x2dii/dbus_launcher /mnt/x2dii/camera/dbus-daemon --config-file=/mnt/x2dii/camera/dbus-local.conf --nofork --nosyslog --nopidfile --print-address > /dev/x2dii-dbus.log 2>&1 &
dbus_pid=$!
sleep 1
cat /dev/x2dii-dbus.log
if ! kill -0 "$dbus_pid"; then
    wait "$dbus_pid"
    echo DBUS_START_RC=$?
    timeout 3 logcat -d -t 100
fi
echo X2DII_CAMERA_START
LD_LIBRARY_PATH=$camera_lib /mnt/x2dii/mock_services "$2" &
mock_pid=$!
sleep 1
date
logcat -v brief -s camera-gui-software:I &
ui_log_pid=$!
if [ "$1" = app ]; then
    export DEVKIT_WIDTH=1024 DEVKIT_HEIGHT=768
    app_entry=${3:-app/hello}
    case "$app_entry" in
        /*|*..*|*[!a-zA-Z0-9_./+-]*) echo X2DII_UI_FAILED; exit 1 ;;
    esac
    if [ ! -f "/mnt/x2dii/$app_entry" ]; then echo X2DII_UI_FAILED; exit 1; fi
    app_lib=${4:-}
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
        (cd "/mnt/x2dii/$app_root" &&
            export LD_LIBRARY_PATH="/mnt/x2dii/$app_lib:$camera_lib" &&
            exec "/mnt/x2dii/$app_entry") &
    else
        LD_LIBRARY_PATH=$camera_lib "/mnt/x2dii/$app_entry" &
    fi
else
    ui_preload=
    [ -f /mnt/x2dii/ion_compat.so ] && ui_preload=/mnt/x2dii/ion_compat.so
    ui_simulation=--simulation
    [ -f /mnt/x2dii/camera/linker ] && ui_simulation=
    ui_platform=wayland-egl
    [ -f /mnt/x2dii/camera/linker ] && ui_platform=wayland
    LD_PRELOAD=$ui_preload LD_LIBRARY_PATH=$camera_lib /mnt/x2dii/camera/camera-gui-software -platform $ui_platform --fullscreen $ui_simulation &
fi
camera_pid=$!
sleep 15
if [ "$1" != app ]; then
if [ -f /mnt/x2dii/camera/linker ]; then
echo 'down 500 650' > /dev/x2dii-input
for y in 600 500 400 300 200 100; do
    echo "move 500 $y" > /dev/x2dii-input
    sleep 0.1
done
echo 'up 500 100' > /dev/x2dii-input
else
echo 'down 900 400' > /dev/x2dii-input
sleep 0.1
for x in 800 700 600 500 400 300 200 100; do
    echo "move $x 400" > /dev/x2dii-input
    sleep 0.1
done
echo 'up 100 400' > /dev/x2dii-input
fi
# Let asynchronous menu loaders and the opening transition finish in guest time.
sleep 3
fi
if [ "$1" = live ] || [ "$1" = app ]; then
    if ! kill -0 "$camera_pid"; then
        wait "$camera_pid"
        echo X2DII_CAMERA_RC=$?
        logcat -d -s camera-gui-software:V libc:F DEBUG:F
        echo X2DII_UI_FAILED
        exit 1
    fi
    echo X2DII_UI_SESSION_READY
    wait "$camera_pid"
    echo X2DII_UI_EXITED
else
if [ "$1" = submenu ]; then
    sleep 3
    echo 'tap 393 390' > /dev/x2dii-input
fi
sleep 15
if kill -0 "$camera_pid"; then
    echo X2DII_CAMERA_ALIVE_AFTER_30S
    echo X2DII_UI_TEST_PASS
    kill -9 "$camera_pid"
fi
wait "$camera_pid"
echo X2DII_CAMERA_RC=$?
fi
date
logcat -d -s camera-gui-software:I camera-gui:I
for crash in /data/tombstones/tombstone_*; do
    [ -f "$crash" ] || continue
    if grep -q 'name: camera-gui' "$crash"; then
        grep -A 35 '^backtrace:' "$crash"
    fi
done
kill "$compositor_pid"
kill "$dbus_pid"
kill "$mock_pid"
kill "$ui_log_pid"
echo X2DII_TEST_COMPLETE
