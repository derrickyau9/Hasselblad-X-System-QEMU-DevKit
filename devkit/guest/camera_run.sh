#!/system/bin/sh
export LD_LIBRARY_PATH=/mnt/x2dii/camera/lib
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
/mnt/x2dii/mini_compositor /dev/block/vdf $fast_input $fast_frames &
compositor_pid=$!
/mnt/x2dii/dbus_launcher /mnt/x2dii/camera/dbus-daemon --config-file=/mnt/x2dii/camera/dbus-local.conf --nofork --nosyslog --nopidfile --print-address > /dev/x2dii-dbus.log 2>&1 &
dbus_pid=$!
sleep 1
cat /dev/x2dii-dbus.log
if ! kill -0 "$dbus_pid"; then
    wait "$dbus_pid"
    echo DBUS_START_RC=$?
    timeout 3 logcat -d -t 100
fi
echo X2DII_CAMERA_START
/mnt/x2dii/mock_services &
mock_pid=$!
sleep 1
date
if [ "$1" = app ]; then
    /mnt/x2dii/app/hello &
else
    /mnt/x2dii/camera/camera-gui-software -platform wayland-egl --fullscreen --simulation &
fi
camera_pid=$!
sleep 15
if [ "$1" != app ]; then
echo 'down 900 400' > /dev/x2dii-input
sleep 0.1
for x in 800 700 600 500 400 300 200 100; do
    echo "move $x 400" > /dev/x2dii-input
    sleep 0.1
done
echo 'up 100 400' > /dev/x2dii-input
fi
if [ "$1" = live ] || [ "$1" = app ]; then
    if ! kill -0 "$camera_pid"; then
        echo X2DII_UI_FAILED
        exit 1
    fi
    echo X2DII_UI_SESSION_READY
    wait "$camera_pid"
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
echo X2DII_TEST_COMPLETE
