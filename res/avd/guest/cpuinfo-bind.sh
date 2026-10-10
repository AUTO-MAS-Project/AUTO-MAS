#!/system/bin/sh
# cpuinfo-bind.sh - one cpuinfo entry per real vCPU for the ARM translation layer. Run as root (su 0 sh ...).
# Same text as the inline script in aemu-lab tools\launcher\avd-p0.ps1; keep the two in sync.
#
# ARM games run through libndk_translation, which answers their /proc/cpuinfo from
# /system/etc/cpuinfo.{arm64,arm}.txt: a single "processor : 1" entry. Unity then reports
# "Cores = 1", starts two job workers and picks the lowest quality preset (Star Rail: VeryLow).
# Bind one entry per real vCPU over both files; zygote's mounts are slaves of / so running
# apps' namespaces see it too. Takes effect when a game process starts. Prints the entry count.
n=$(grep -c ^processor /proc/cpuinfo)
mkdir -p /data/local/tmp/cpuinfo
for a in arm64 arm; do
  src=/system/etc/cpuinfo.$a.txt; dst=/data/local/tmp/cpuinfo/cpuinfo.$a.txt
  grep -q " $src " /proc/self/mountinfo && continue
  : > $dst
  i=0
  while [ $i -lt $n ]; do sed "s/^processor\t: .*/processor\t: $i/" $src >> $dst; echo >> $dst; i=$((i+1)); done
  chmod 644 $dst; chcon u:object_r:system_file:s0 $dst; mount --bind $dst $src
done
grep -c ^processor /system/etc/cpuinfo.arm64.txt
