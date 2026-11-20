using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

// 每种目录用途独立解析。卷容量按卷去重，磁盘性能只绑定单盘 extent。
sealed class Storage
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint creation,
                                            uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern uint GetFinalPathNameByHandle(SafeFileHandle file, StringBuilder path, uint size, uint flags);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool GetVolumeInformation(string root, IntPtr label, int labelSize, IntPtr serial, IntPtr max,
                                            IntPtr flags, StringBuilder fs, int fsSize);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool GetDiskFreeSpaceEx(string path, out ulong available, out ulong total, out ulong free);
    [DllImport("kernel32.dll")]
    static extern bool DeviceIoControl(SafeFileHandle file, uint code, byte[] input, int insize, byte[] output,
                                       int outsize, out int returned, IntPtr overlapped);
    sealed class Volume
    {
        public string Root, Fs, Media, Bus;
        public int Disk = -1;
        public double Available, Capacity, Used;
    }
    readonly Dictionary<string, Volume> roles = new Dictionary<string, Volume>();
    readonly Dictionary<string, Volume> volumes = new Dictionary<string, Volume>(StringComparer.OrdinalIgnoreCase);
    static string FinalVolume(string path)
    {
        while (!String.IsNullOrEmpty(path))
        {
            using (var file = CreateFile(path, 0, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero))
            {
                if (!file.IsInvalid)
                {
                    var resolved = new StringBuilder(32768);
                    uint n = GetFinalPathNameByHandle(file, resolved, (uint)resolved.Capacity, 1);
                    string full = resolved.ToString();
                    int end = full.IndexOf("}\\", StringComparison.Ordinal);
                    if (n > 0 && n < resolved.Capacity &&
                        full.StartsWith(@"\\?\Volume{", StringComparison.OrdinalIgnoreCase) && end > 0)
                        return full.Substring(0, end + 2);
                    resolved.Clear();
                    n = GetFinalPathNameByHandle(file, resolved, (uint)resolved.Capacity, 0);
                    full = resolved.ToString();
                    if (n > 0 && n < resolved.Capacity &&
                        full.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase))
                        return Path.GetPathRoot(@"\\" + full.Substring(8)).TrimEnd('\\') + @"\";
                    return null;
                }
                int err = Marshal.GetLastWin32Error();
                if (err != 2 && err != 3)
                    return null;
                // 存在但目标不可用的重解析点不能按上级卷归类。
                try
                {
                    if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                        return null;
                }
                catch (FileNotFoundException)
                {
                }
                catch (DirectoryNotFoundException)
                {
                }
            }
            path = Path.GetDirectoryName(path);
        }
        return null;
    }
    static Volume Inspect(string root)
    {
        var v = new Volume { Root = root };
        var fs = new StringBuilder(32);
        if (GetVolumeInformation(root, IntPtr.Zero, 0, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, fs, 32))
            v.Fs = fs.ToString().ToLowerInvariant();
        if (root.StartsWith(@"\\", StringComparison.Ordinal) && !root.StartsWith(@"\\?\", StringComparison.Ordinal))
        {
            v.Bus = "network";
            return v;
        }
        using (var h = CreateFile(root.TrimEnd('\\'), 0, 7, IntPtr.Zero, 3, 0, IntPtr.Zero))
        {
            var buf = new byte[256];
            int got;
            if (!h.IsInvalid && DeviceIoControl(h, 0x560000, null, 0, buf, buf.Length, out got, IntPtr.Zero) &&
                got >= 32 && BitConverter.ToUInt32(buf, 0) == 1)
                v.Disk = BitConverter.ToInt32(buf, 8);
        }
        if (v.Disk < 0)
            return v;
        using (var h = CreateFile(@"\\.\PhysicalDrive" + v.Disk, 0, 7, IntPtr.Zero, 3, 0, IntPtr.Zero))
        {
            if (h.IsInvalid)
                return v;
            var input = new byte[12];
            var buf = new byte[4096];
            int got;
            if (DeviceIoControl(h, 0x2d1400, input, input.Length, buf, buf.Length, out got, IntPtr.Zero) && got >= 32)
            {
                switch (BitConverter.ToUInt32(buf, 28))
                {
                case 1:
                    v.Bus = "scsi";
                    break;
                case 7:
                    v.Bus = "usb";
                    break;
                case 8:
                    v.Bus = "raid";
                    break;
                case 10:
                    v.Bus = "sas";
                    break;
                case 11:
                    v.Bus = "sata";
                    break;
                case 14:
                case 15:
                case 16:
                    v.Bus = "virtual";
                    break;
                case 17:
                    v.Bus = "nvme";
                    break;
                default:
                    v.Bus = "other";
                    break;
                }
            }
            // 虚拟磁盘与 RAID 的系统磁盘号不能证明物理介质归属。
            if (v.Bus == "virtual" || v.Bus == "raid")
            {
                v.Disk = -1;
                return v;
            }
            input[0] = 7;
            if (DeviceIoControl(h, 0x2d1400, input, input.Length, buf, buf.Length, out got, IntPtr.Zero) && got >= 9 &&
                v.Bus != "virtual" && v.Bus != "raid")
                v.Media = buf[8] != 0 ? "hdd" : "ssd";
        }
        return v;
    }
    public Storage(string[] paths, string[] names)
    {
        for (int i = 0; i < names.Length; i++)
        {
            if (String.IsNullOrEmpty(paths[i]))
                continue;
            try
            {
                string root = FinalVolume(paths[i]);
                if (root == null)
                    continue;
                Volume volume;
                if (!volumes.TryGetValue(root, out volume))
                    volumes[root] = volume = Inspect(root);
                roles[names[i]] = volume;
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
            catch (ArgumentException)
            {
            }
        }
    }
    public void Sample(Dictionary<string, object> row, Counters counters)
    {
        foreach (var v in volumes.Values)
        {
            ulong available, total, free;
            if (GetDiskFreeSpaceEx(v.Root, out available, out total, out free) && total > 0)
            {
                v.Available = available / 1073741824.0;
                v.Capacity = total / 1073741824.0;
                v.Used = 100.0 * (1 - available / (double)total);
            }
            else
                v.Capacity = 0;
        }
        Volume install;
        roles.TryGetValue("install", out install);
        foreach (var role in roles)
        {
            string prefix = role.Key + "_";
            var v = role.Value;
            if (v.Capacity > 0)
            {
                row[prefix + "capacity"] = v.Capacity;
                row[prefix + "free"] = v.Available;
                row[prefix + "used"] = v.Used;
            }
            row[prefix + "fs"] = v.Fs;
            row[prefix + "bus"] = v.Bus;
            row[prefix + "media"] = v.Media;
            row[prefix + "location"] = install == null                  ? "unknown"
                                         : v == install                   ? "same-volume"
                                         : v.Disk < 0 || install.Disk < 0 ? "unknown"
                                         : v.Disk == install.Disk         ? "same-disk"
                                                                          : "different-disk";
        }
        foreach (string metric in new[] { "busy", "read_latency", "write_latency", "read_speed", "write_speed", "iops",
                                          "queue" })
        {
            foreach (var item in counters.Read(metric))
            {
                int disk;
                if (!Int32.TryParse(item.Key.Split(' ')[0], out disk))
                    continue;
                foreach (var role in roles)
                    if (role.Value.Disk == disk)
                    {
                        double n = item.Value;
                        if (metric == "busy")
                            n = Math.Max(0, 100 - n);
                        if (metric.EndsWith("_latency"))
                            n *= 1000;
                        if (metric.EndsWith("_speed"))
                            n /= 1048576;
                        row[role.Key + "_" + metric] = n;
                    }
            }
        }
    }
}
