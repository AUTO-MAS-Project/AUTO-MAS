using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

static class Probe
{
    [StructLayout(LayoutKind.Sequential)]
    struct Memory
    {
        public uint Length, Load;
        public ulong Total, Available, TotalPage, AvailablePage, Virtual, AvailableVirtual, Extended;
    }
    [DllImport("kernel32.dll")]
    static extern bool GlobalMemoryStatusEx(ref Memory status);
    static readonly string[] roles = { "install",       "workspace",    "cache",         "python",          "venv",
                                       "electron_temp", "backend_temp", "runtime_build", "runtime_download" };
    static void CpuInventory(Dictionary<string, object> row)
    {
        using (
            var query = new ManagementObjectSearcher(
                "SELECT Name, NumberOfCores, NumberOfLogicalProcessors FROM Win32_Processor")) using (var items =
                                                                                                          query.Get())
        {
            int cores = 0, logical = 0;
            foreach (ManagementObject p in items)
                using (p)
                {
                    row["cpu_series"] = p["Name"];
                    cores += Convert.ToInt32(p["NumberOfCores"]);
                    logical += Convert.ToInt32(p["NumberOfLogicalProcessors"]);
                }
            if (cores > 0)
                row["physical_cores"] = cores;
            if (logical > 0)
                row["logical_cores"] = logical;
        }
    }
    static int Main(string[] args)
    {
        if (args.Length != roles.Length + 1)
            return 2;
        var clock = Stopwatch.StartNew();
        int parent;
        if (!Int32.TryParse(args[0], out parent))
            return 2;
        var owned = new OwnedProcesses(parent);
        var paths = new string[roles.Length];
        Array.Copy(args, 1, paths, 0, paths.Length);
        // 宿主崩溃也会关闭管道，阻塞的系统查询不会遗留探针。
        var owner = new Thread(delegate() {
            Console.In.ReadToEnd();
            Environment.Exit(0);
        });
        owner.IsBackground = true;
        owner.Start();
        var json = new JavaScriptSerializer();
        var inventory = new Dictionary<string, object>();
        try
        {
            CpuInventory(inventory);
        }
        catch (ManagementException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
        try
        {
            using (var virtualDisplays = new ManagementObjectSearcher(
                       "SELECT PNPDeviceID FROM Win32_VideoController")) using (var displays = virtualDisplays.Get())
            {
                int count = 0;
                foreach (ManagementObject d in displays)
                    using (d)
                    {
                        string id = Convert.ToString(d["PNPDeviceID"]);
                        if (id.StartsWith(@"ROOT\", StringComparison.OrdinalIgnoreCase) ||
                            id.StartsWith(@"SWD\", StringComparison.OrdinalIgnoreCase))
                            count++;
                    }
                inventory["virtual_adapters"] = count;
            }
        }
        catch (ManagementException)
        {
        }
        catch (UnauthorizedAccessException)
        {
        }
        var storage = new Storage(paths, roles);
        var gpu = new Adapters();
        using (var counters = new Counters())
        {
            for (int sample = 0; clock.Elapsed.TotalMinutes < 10; sample++)
            {
                var tick = Stopwatch.StartNew();
                if (sample > 0)
                    counters.Collect();
                var row = new Dictionary<string, object>(inventory);
                var mem = new Memory { Length = (uint)Marshal.SizeOf(typeof(Memory)) };
                if (GlobalMemoryStatusEx(ref mem))
                {
                    row["ram"] = mem.Total / 1073741824.0;
                    row["ram_free"] = mem.Available / 1073741824.0;
                    row["ram_used"] = 100.0 * (1 - mem.Available / (double)mem.Total);
                }

                foreach (var v in counters.Read("commit"))
                    row["commit"] = v.Value;
                foreach (var v in counters.Read("cpu"))
                {
                    if (String.Equals(v.Key, "_Total", StringComparison.OrdinalIgnoreCase))
                        row["cpu"] = v.Value;
                    else
                    {
                        object highest;
                        if (!row.TryGetValue("core", out highest) || v.Value > (double)highest)
                            row["core"] = v.Value;
                    }
                }
                owned.Sample(row);
                gpu.Sample(row, counters);
                storage.Sample(row, counters);
                Console.WriteLine(json.Serialize(row));
                Console.Out.Flush();
                Thread.Sleep(Math.Max(1, 1000 - (int)tick.ElapsedMilliseconds));
            }
        }
        return 0;
    }
}
