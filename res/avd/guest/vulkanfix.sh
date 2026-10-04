#!/system/bin/sh
# vulkanfix.sh <orig sha256> <patched sha256> - bind-mount the patched guest Vulkan encoder over the image's own and
# restart zygote (it preloads the driver). Run as root (su 0 sh ...). Same steps as -VulkanFix in aemu-lab
# tools\launcher\avd-p0.ps1; the patch itself is made on the host from the image's own library (khrfix), the
# patched file is never shipped.
#
# The API 34 image's /vendor/lib64/libvulkan_enc.so routes vkUpdateDescriptorSetWithTemplateKHR to the raw encoder,
# which sends the descriptor payload as one byte; Star Rail (Vulkan "normal mode") then draws with descriptors that
# were never written and the GPU faults.
#
# The patched copy stays in /data/local/tmp as a cache: the next boot mounts it again without a new upload. It is
# relabelled for /vendor and then no longer writable by adb, so the host uploads under a separate name.
#
# Prints one status word first: MOUNTED (done now, zygote restarted), ALREADY (mounted earlier this boot),
# NEED_UPLOAD (no valid cached copy: upload the patched file to $u and run again), SKIPPED image (the image's
# library has an unexpected hash: nothing changed), SKIPPED patched (the copy in $p is bad: it is removed, nothing
# mounted; the next run asks for a new upload).
v=/vendor/lib64/libvulkan_enc.so
p=/data/local/tmp/libvulkan_enc.khrfix.so
u=/data/local/tmp/khrfix-upload.so
orig=$1
fix=$2
if grep -q " $v " /proc/self/mountinfo; then echo "ALREADY"; exit 0; fi
[ "$(sha256sum $v | cut -d' ' -f1)" = "$orig" ] || { echo "SKIPPED image library $(sha256sum $v | cut -d' ' -f1)"; exit 0; }
if [ "$(sha256sum $p 2>/dev/null | cut -d' ' -f1)" != "$fix" ]; then
  [ "$(sha256sum $u 2>/dev/null | cut -d' ' -f1)" = "$fix" ] || { echo "NEED_UPLOAD"; exit 0; }
  rm -f $p; cp $u $p; rm -f $u
fi
[ "$(sha256sum $p | cut -d' ' -f1)" = "$fix" ] || { rm -f $p; echo "SKIPPED patched copy hash mismatch"; exit 0; }
chmod 644 $p; chcon $(ls -Z $v | cut -d' ' -f1) $p; mount --bind $p $v
setprop ctl.restart zygote
echo "MOUNTED zygote restarted"
