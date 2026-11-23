using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// PDH 的英文计数器路径不依赖 Windows 的显示语言。
sealed class Counters : IDisposable
{
    [DllImport("pdh.dll")]
    static extern uint PdhOpenQueryW(IntPtr data, UIntPtr user, out IntPtr query);
    [DllImport("pdh.dll", CharSet = CharSet.Unicode)]
    static extern uint PdhAddEnglishCounterW(IntPtr query, string path, UIntPtr user, out IntPtr counter);
    [DllImport("pdh.dll")]
    static extern uint PdhCollectQueryData(IntPtr query);
    [DllImport("pdh.dll")]
    static extern uint PdhCloseQuery(IntPtr query);
    [DllImport("pdh.dll")]
    static extern uint PdhGetFormattedCounterArrayW(IntPtr counter, uint format, ref uint bytes, out uint items,
                                                    IntPtr buffer);
    [DllImport("pdh.dll")]
    static extern uint PdhGetFormattedCounterValue(IntPtr counter, uint format, IntPtr type, out Value value);
    [StructLayout(LayoutKind.Sequential)]
    struct Value
    {
        public uint Status;
        public double Number;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Item
    {
        public IntPtr Name;
        public Value Value;
    }
    readonly Dictionary<string, IntPtr> handles = new Dictionary<string, IntPtr>();
    IntPtr query;
    public Counters()
    {
        if (PdhOpenQueryW(IntPtr.Zero, UIntPtr.Zero, out query) != 0)
            return;
        Add("cpu", @"\Processor(*)\% Processor Time");
        Add("commit", @"\Memory\% Committed Bytes In Use");
        Add("gpu", @"\GPU Engine(*)\Utilization Percentage");
        Add("dedicated", @"\GPU Adapter Memory(*)\Dedicated Usage");
        Add("shared", @"\GPU Adapter Memory(*)\Shared Usage");
        Add("busy", @"\PhysicalDisk(*)\% Idle Time");
        Add("read_latency", @"\PhysicalDisk(*)\Avg. Disk sec/Read");
        Add("write_latency", @"\PhysicalDisk(*)\Avg. Disk sec/Write");
        Add("read_speed", @"\PhysicalDisk(*)\Disk Read Bytes/sec");
        Add("write_speed", @"\PhysicalDisk(*)\Disk Write Bytes/sec");
        Add("iops", @"\PhysicalDisk(*)\Disk Transfers/sec");
        Add("queue", @"\PhysicalDisk(*)\Current Disk Queue Length");
        Collect();
    }
    void Add(string key, string path)
    {
        IntPtr h;
        if (PdhAddEnglishCounterW(query, path, UIntPtr.Zero, out h) == 0)
            handles.Add(key, h);
    }
    public void Collect()
    {
        if (query != IntPtr.Zero)
            PdhCollectQueryData(query);
    }
    public Dictionary<string, double> Read(string key)
    {
        var values = new Dictionary<string, double>(StringComparer.OrdinalIgnoreCase);
        IntPtr h;
        if (!handles.TryGetValue(key, out h))
            return values;
        uint bytes = 0, items;
        const uint format = 0x200 | 0x8000;
        if (key == "commit")
        {
            Value v;
            if (PdhGetFormattedCounterValue(h, format, IntPtr.Zero, out v) == 0 && v.Status <= 1)
                values[""] = v.Number;
            return values;
        }
        if (PdhGetFormattedCounterArrayW(h, format, ref bytes, out items, IntPtr.Zero) != 0x800007D2 ||
            bytes > 8 * 1024 * 1024)
            return values;
        IntPtr buffer = Marshal.AllocHGlobal((int)bytes);
        try
        {
            if (PdhGetFormattedCounterArrayW(h, format, ref bytes, out items, buffer) != 0)
                return values;
            int size = Marshal.SizeOf(typeof(Item));
            for (int i = 0; i < items; i++)
            {
                var item = (Item)Marshal.PtrToStructure(IntPtr.Add(buffer, i * size), typeof(Item));
                double n = item.Value.Number;
                if (item.Value.Status <= 1 && !Double.IsNaN(n) && !Double.IsInfinity(n) && n >= 0)
                    values[Marshal.PtrToStringUni(item.Name) ?? ""] = n;
            }
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
        return values;
    }
    public void Dispose()
    {
        if (query != IntPtr.Zero)
            PdhCloseQuery(query);
    }
}
