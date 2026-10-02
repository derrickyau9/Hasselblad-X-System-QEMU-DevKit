#!/system/bin/sh
# Unpack the user's Linux UI into the disposable guest's data disk.
root=/mnt/x1d/root
fail() { echo X2DII_UI_FAILED; exit 1; }
mount -o remount,rw / || fail
mkdir -p /mnt/x1d
mount -t ext4 /dev/block/vdg /mnt/x1d || fail
if [ ! -f "$root/.devkit-ready" ]; then
    echo LEGACY_UNPACK_FIRMWARE
    mkdir -p "$root"
    tar -xf /mnt/x2dii/rootfs.tar -C "$root" || fail
    echo LEGACY_UNPACK_RUNTIME
    tar -xzf /mnt/x2dii/compat.tar.gz -C "$root" || fail
    touch "$root/.devkit-ready"
fi
echo LEGACY_CHROOT_START
for folder in dev proc sys; do
    mkdir -p "$root/$folder"
    mount -o bind "/$folder" "$root/$folder"
done
mkdir -p "$root/devkit"
mount -o bind /mnt/x2dii "$root/devkit"
chroot "$root" /bin/sh /devkit/camera/linux_ui.sh "$1" "$3" "$4" || fail
