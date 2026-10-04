#!/system/bin/sh
# mas-wifi-fastpath.sh - guest sees Wi-Fi, bulk data goes over eth0. Run as root
# (adb root + adb shell, or adb shell su 0 sh ...). Same text is embedded in
# external/qemu android/android-emu/android/network/wifi.cpp (-wifi-fastpath);
# keep the two in sync. Explanation: C:\emu-src\patches\wifi\README.md
#
#   on      apply once (idempotent)
#   daemon  start "watch" in the background unless already running
#   watch   loop: re-apply every 10 s (rules after a netd restart, TCP buffers
#           after every default-network change)
#   off     stop the watcher and remove the rules
#   status  print current state
#
# How: Wi-Fi (wlan0, virtio mac80211_hwsim) stays connected, so the default
# network, NetworkCapabilities and what apps see stay WIFI. One ip rule placed
# before every per-network rule netd installs sends locally generated traffic
# to eth0's table (eth0 = mobile data, plain virtio-net). Sockets pinned to
# wlan0 with SO_BINDTODEVICE (DHCP renewals) find no dev-wlan0 route in that
# table and fall through to netd's rules. If eth0 goes away netd empties its
# table and the rule becomes inert: traffic falls back to Wi-Fi, never breaks.
#
# Do NOT run `emu gsm meter on|off` together with this: the image's
# com.android.emulator.radio.config MeterService then installs a 2 GB
# SubscriptionPlan on the radio link; at the limit mobile data is switched off
# and everything falls back to the slow Wi-Fi path.
PREF=15000
RMEM='2097152 6291456 16777216'
WMEM='512000 2097152 8388608'
TAG=mas-wifi-fastpath

say() { echo "$TAG: $*"; /system/bin/log -t $TAG "$*" 2>/dev/null; }

has_rule() { ip $1 rule show 2>/dev/null | grep -q "^$PREF:.*lookup eth0"; }

apply() {
    has_rule -4 || { ip -4 rule add pref $PREF iif lo lookup eth0 && say "ipv4 rule added"; }
    has_rule -6 || { ip -6 rule add pref $PREF iif lo lookup eth0 && say "ipv6 rule added"; }
    # Wi-Fi as default network sets tcp_rmem/wmem to Wi-Fi's 512K/1M/2M; use
    # eth0's sizes while eth0 is up (29 -> 35 MB/s locally, more on high RTT).
    if ip -4 route show table eth0 2>/dev/null | grep -q '^default'; then
        [ "$(cat /proc/sys/net/ipv4/tcp_rmem)" = "$(echo $RMEM | tr ' ' '\t')" ] || echo "$RMEM" > /proc/sys/net/ipv4/tcp_rmem
        [ "$(cat /proc/sys/net/ipv4/tcp_wmem)" = "$(echo $WMEM | tr ' ' '\t')" ] || echo "$WMEM" > /proc/sys/net/ipv4/tcp_wmem
    fi
}

case "$1" in
on)
    # keep mobile data up while Wi-Fi is validated (image default is 1)
    [ "$(settings get global mobile_data_always_on 2>/dev/null)" = 1 ] || settings put global mobile_data_always_on 1
    apply
    dumpsys netpolicy | grep -q 'SubscriptionPlan{' && say "WARNING: SubscriptionPlan present (gsm meter was used); mobile data is cut at its limit, reboot to clear"
    ;;
daemon)
    pgrep -f "$TAG.sh watch" >/dev/null || { nohup setsid sh "$0" watch >/dev/null 2>&1 & }
    ;;
watch)
    say "watch start pid $$"
    while true; do apply; sleep 10; done
    ;;
off)
    for p in $(pgrep -f "$TAG.sh watch"); do [ "$p" != "$$" ] && kill $p; done
    while ip -4 rule del pref $PREF 2>/dev/null; do :; done
    while ip -6 rule del pref $PREF 2>/dev/null; do :; done
    say "off"
    ;;
status)
    echo "rule4: $(ip -4 rule show | grep "^$PREF:")"
    echo "rule6: $(ip -6 rule show | grep "^$PREF:")"
    echo "eth0 default: $(ip -4 route show table eth0 2>/dev/null | grep '^default')"
    echo "route 1.1.1.1: $(ip route get 1.1.1.1 | head -1)"
    echo "tcp_rmem: $(cat /proc/sys/net/ipv4/tcp_rmem)"
    echo "eth0 quota: $(iptables -w -S bw_costly_eth0 2>/dev/null | grep -o 'quota [0-9]*' || echo none)"
    echo "data plan: $(dumpsys netpolicy | grep -o 'dataLimitBytes=[0-9]*' || echo none)"
    echo "watchers: $(pgrep -f "$TAG.sh watch" | tr '\n' ' ')"
    echo "default network: $(dumpsys connectivity | grep -m1 -oE 'Active default network: [0-9]+')"
    dumpsys connectivity | grep -oE 'ni\{[A-Z]+[^ ]* [A-Z]+' | sort -u
    ;;
*)
    echo "usage: $0 on|daemon|watch|off|status"; exit 2
    ;;
esac
