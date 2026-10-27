#!/system/bin/sh
# vulkanfix.sh <orig sha256> <patched sha256> - bind-mount the patched guest Vulkan encoder (bindlock2, includes
# khrfix) over the image's own and restart zygote (it preloads the driver). Run as root (su 0 sh ...). Same steps as
# -VulkanFix in aemu-lab tools\launcher\avd-p0.ps1; the patch itself is made on the host from the image's own library
# (app/utils/common/emulator2/avd/vulkanfix.py), the patched file is never shipped.
#
# The patched copy stays in /data/local/tmp as a cache: the next boot mounts it again without a new upload. It is
# relabelled for /vendor and then no longer writable by adb, so the host uploads under a separate name.
#
# Prints one status line, first word:
#   MOUNTED <sha256>        mounted now and zygote restarted
#   ALREADY <sha256>        something is already mounted over the library this boot (its hash follows)
#   VENDOR_PATCHED          the image's own library already is the patched one: nothing to do
#   NEED_UPLOAD             no valid cached copy: upload the patched file to $u and run again
#   SKIPPED image <sha256>  the image's library has an unexpected hash: nothing changed
#   SKIPPED patched <sha256> the copy in $p is bad: removed, nothing mounted; the next run asks for a new upload
#   FAILED <step> ...       chcon / mount did not take: nothing left mounted, zygote not restarted
v=/vendor/lib64/libvulkan_enc.so
p=/data/local/tmp/libvulkan_enc.khrfix-bindlock2.so
u=/data/local/tmp/vulkanfix-upload.so
orig=$1
fix=$2
if grep -q " $v " /proc/self/mountinfo; then echo "ALREADY $(sha256sum $v | cut -d' ' -f1)"; exit 0; fi
cur=$(sha256sum $v | cut -d' ' -f1)
[ "$cur" = "$fix" ] && { echo "VENDOR_PATCHED"; exit 0; }
[ "$cur" = "$orig" ] || { echo "SKIPPED image $cur"; exit 0; }
if [ "$(sha256sum $p 2>/dev/null | cut -d' ' -f1)" != "$fix" ]; then
  [ "$(sha256sum $u 2>/dev/null | cut -d' ' -f1)" = "$fix" ] || { rm -f $u; echo "NEED_UPLOAD"; exit 0; }
  rm -f $p; cp $u $p; rm -f $u
fi
got=$(sha256sum $p | cut -d' ' -f1)
[ "$got" = "$fix" ] || { rm -f $p; echo "SKIPPED patched $got"; exit 0; }
label=$(ls -Z $v | cut -d' ' -f1)
chmod 644 $p
chcon $label $p
[ "$(ls -Z $p | cut -d' ' -f1)" = "$label" ] || { echo "FAILED chcon $label -> $(ls -Z $p | cut -d' ' -f1)"; exit 0; }
mount --bind $p $v
got=$(sha256sum $v | cut -d' ' -f1)
if [ "$got" != "$fix" ]; then
  grep -q " $v " /proc/self/mountinfo && umount $v
  echo "FAILED mount $got"
  exit 0
fi
setprop ctl.restart zygote
echo "MOUNTED $got"
