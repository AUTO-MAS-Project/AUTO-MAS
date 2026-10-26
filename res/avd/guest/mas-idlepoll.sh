#!/system/bin/sh
# mas-idlepoll.sh - keep the vCPUs from halting while /data does many small
# requests. Run as root (adb shell su 0 sh ...).
#
#   daemon  start "watch" in the background unless already running; exits 1
#           with the reason when the data disk's counters cannot be read
#   watch   loop: every 0.2 s count the data disk's completed requests; at
#           >= ON per second start one SCHED_IDLE busy loop per CPU, below
#           OFF per second for 1 s stop them
#   off     stop the watcher and the loops
#   status  print current state
#
# Why: with the local APIC emulated by Hyper-V (WHPX kernel irqchip) a halted
# vCPU waits inside the hypervisor, and every disk completion first has to wake
# it (about 60 us of the ~180 us a request takes). Some games fsync after every
# 8 KB while downloading (Arknights: write 8 KB + fsync, ~1000 journal commits
# per second), so the download runs at the speed of that round trip: about
# 7-9 MB/s here, 7-11 MB/s on MuMu, 10-11 MB/s with the loops (10-21 A/B,
# 457 MB update: 49-62 s -> 38-47 s). SCHED_IDLE tasks only run when a CPU
# would otherwise be idle, so they take no time from real work; the cost is
# host CPU, about two cores for as long as the burst lasts.
ON=400
OFF=200
TAG=mas-idlepoll

say() { echo "$TAG: $*"; /system/bin/log -t $TAG "$*" 2>/dev/null; }

# /data sits on dm-default-key (metadata encryption) over the virtio disk:
# count the disk itself, the numbers above were measured there.
# /sys/class/block also has partitions, /sys/block only whole disks.
data_disk() {
    d=$(awk '$2 == "/data" {print $1; exit}' /proc/mounts)
    d=${d##*/}
    for s in /sys/class/block/$d/slaves/*; do
        [ -e "$s" ] && { d=${s##*/}; break; }
    done
    echo $d
}

requests() { awk '{print $1 + $5}' /sys/class/block/$1/stat; }

case "$1" in
daemon)
    disk=$(data_disk)
    [ -r /sys/class/block/$disk/stat ] || { say "no stat for the data disk '$disk', not watching"; exit 1; }
    pgrep -f "$TAG.sh watch" >/dev/null || { nohup setsid sh "$0" watch >/dev/null 2>&1 & }
    # return once the watcher is visible, so a status right after this sees it
    i=0
    while [ $i -lt 10 ] && ! pgrep -f "$TAG.sh watch" >/dev/null; do sleep 0.1; i=$((i + 1)); done
    ;;
watch)
    disk=$(data_disk)
    [ -r /sys/class/block/$disk/stat ] || { say "no stat for the data disk '$disk', not watching"; exit 1; }
    # two daemon calls racing can start two watchers: the lowest pid stays
    for p in $(pgrep -f "$TAG.sh watch"); do
        [ "$p" -lt $$ ] && exit 0
    done
    # loops left behind by an older watcher (they also stop by themselves
    # within a moment once their watcher is gone, see SPIN)
    pkill -f "$TAG-spin"
    # each loop checks that this watcher still exists, so a watcher killed
    # without its trap running (SIGKILL) does not leave them spinning
    SPIN="while [ -d /proc/$$ ]; do :; done # $TAG-spin"
    cpus=$(grep -c ^processor /proc/cpuinfo)
    say "watch start pid $$ disk $disk cpus $cpus on $ON/s off $OFF/s"
    loops=""
    trap 'kill $loops 2>/dev/null; exit 0' TERM INT
    quiet=0
    prev=$(requests $disk)
    while true; do
        sleep 0.2
        cur=$(requests $disk)
        rate=$(( (cur - prev) * 5 ))
        prev=$cur
        if [ -z "$loops" ]; then
            [ $rate -ge $ON ] || continue
            i=0
            while [ $i -lt $cpus ]; do
                # exec: $! must be the looping process itself (kill, pgrep)
                (exec chrt -i 0 sh -c "$SPIN") & loops="$loops $!"
                i=$((i + 1))
            done
            quiet=0
        else
            if [ $rate -lt $OFF ]; then quiet=$((quiet + 1)); else quiet=0; fi
            if [ $quiet -ge 5 ]; then
                kill $loops 2>/dev/null
                loops=""
            fi
        fi
    done
    ;;
off)
    for p in $(pgrep -f "$TAG.sh watch"); do [ "$p" != "$$" ] && kill $p; done
    pkill -f "$TAG-spin"
    # the watcher acts on TERM once its current "sleep 0.2" returns
    i=0
    while [ $i -lt 10 ] && pgrep -f "$TAG.sh watch" >/dev/null; do sleep 0.1; i=$((i + 1)); done
    say "off"
    ;;
status)
    echo "disk: $(data_disk)"
    echo "watchers: $(pgrep -f "$TAG.sh watch" | tr '\n' ' ')"
    echo "loops: $(pgrep -f "$TAG-spin" | tr '\n' ' ')"
    for p in $(pgrep -f "$TAG-spin"); do chrt -p $p | grep -o 'SCHED_[A-Z]*'; done | sort | uniq -c
    ;;
*)
    echo "usage: $0 daemon|watch|off|status"; exit 2
    ;;
esac
