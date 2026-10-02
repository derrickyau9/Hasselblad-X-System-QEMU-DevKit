#!/system/bin/sh
# Optional QEMU user-mode networking for the X2D II ARM64 app guest only.
# This runs inside the disposable guest; no physical camera is connected.
fail() { echo "DEVKIT_NETWORK_FAILED: $1"; exit 1; }
run() {
    "$@"
    status=$?
    [ "$status" -eq 0 ] || fail "$* (exit $status)"
}
run_ndc() {
    result=$(ndc "$@" 2>&1)
    status=$?
    echo "$result"
    [ "$status" -eq 0 ] || fail "ndc $* (exit $status)"
    case "$result" in
        '200 0 '*) ;;
        *) fail "ndc $*: $result" ;;
    esac
}
create_network() {
    attempt=0
    while [ "$attempt" -lt 30 ]; do
        result=$(ndc network create 100 2>&1)
        case "$result" in
            '200 0 '*) echo "$result"; return 0 ;;
            *'Error connecting'*) attempt=$((attempt + 1)); sleep 1 ;;
            *) fail "ndc network create 100: $result" ;;
        esac
    done
    fail 'Android netd was unavailable after 30 seconds'
}
[ -e /sys/class/net/eth0 ] || fail 'virtio-net eth0 is missing'
case "$1" in
    ''|*[!0-9]*) fail 'missing host UTC epoch' ;;
esac
[ "$1" -ge 1600000000 ] || fail 'invalid host UTC epoch'
run date -u "@$1"
run ip link set eth0 up
run ip address add 10.0.2.15/24 dev eth0
# Android's initial rules end in an unreachable rule and do not consult main.
run ip rule add pref 100 lookup main
run ip route add default via 10.0.2.2 dev eth0
create_network
run_ndc network interface add 100 eth0
run_ndc network route add 100 eth0 10.0.2.0/24
run_ndc network route add 100 eth0 0.0.0.0/0 10.0.2.2
run_ndc network default set 100
run_ndc resolver setnetdns 100 '' 10.0.2.3
run setprop net.dns1 10.0.2.3
# NetSurf's private glibc resolver reads this file instead of Android netd.
# The system drive is a QEMU snapshot for each session.
run mount -o remount,rw /
printf 'nameserver 10.0.2.3\n' > /etc/resolv.conf || fail 'could not write guest resolv.conf'
echo DEVKIT_NETWORK_READY
