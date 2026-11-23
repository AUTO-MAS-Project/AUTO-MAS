using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

// 仅对本次桌面进程及仍可确认的后代取进程时间；进程创建时刻防止 PID 复用。
sealed class OwnedProcesses
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Entry
    {
        public uint Size, Usage, Pid;
        public UIntPtr Heap;
        public uint Module, Threads, Parent;
        public int Priority;
        public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string Exe;
    }
    [DllImport("kernel32.dll")]
    static extern IntPtr CreateToolhelp32Snapshot(uint flags, uint pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool Process32FirstW(IntPtr handle, ref Entry entry);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool Process32NextW(IntPtr handle, ref Entry entry);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);
    readonly int root, self;
    readonly DateTime rootStart;
    Dictionary<int, TimeSpan> cpu = new Dictionary<int, TimeSpan>();
    Dictionary<int, DateTime> starts = new Dictionary<int, DateTime>();
    readonly Stopwatch clock = Stopwatch.StartNew();
    double previous;
    public OwnedProcesses(int parent)
    {
        root = parent;
        using (var p = Process.GetProcessById(root)) rootStart = p.StartTime.ToUniversalTime();
        using (var p = Process.GetCurrentProcess()) self = p.Id;
    }
    public void Sample(Dictionary<string, object> row)
    {
        var snapshot = CreateToolhelp32Snapshot(2, 0);
        if (snapshot == new IntPtr(-1))
            return;
        var children = new Dictionary<int, List<int>>();
        try
        {
            var entry = new Entry { Size = (uint)Marshal.SizeOf(typeof(Entry)) };
            if (!Process32FirstW(snapshot, ref entry))
                return;
            do
            {
                List<int> list;
                int parent = (int)entry.Parent;
                if (!children.TryGetValue(parent, out list))
                    children[parent] = list = new List<int>();
                list.Add((int)entry.Pid);
            } while (Process32NextW(snapshot, ref entry));
        }
        finally
        {
            CloseHandle(snapshot);
        }
        var pending = new Queue<KeyValuePair<int, DateTime>>();
        pending.Enqueue(new KeyValuePair<int, DateTime>(root, rootStart));
        var next = new Dictionary<int, TimeSpan>();
        var newStarts = new Dictionary<int, DateTime>();
        long memory = 0;
        double used = 0;
        bool measured = false;
        while (pending.Count > 0)
        {
            var item = pending.Dequeue();
            int pid = item.Key;
            if (pid == self || next.ContainsKey(pid))
                continue;
            try
            {
                using (var proc = Process.GetProcessById(pid))
                {
                    var start = proc.StartTime.ToUniversalTime();
                    if (start < item.Value || (pid == root && start != rootStart))
                        continue;
                    var elapsed = proc.TotalProcessorTime;
                    next[pid] = elapsed;
                    newStarts[pid] = start;
                    memory += proc.PrivateMemorySize64;
                    TimeSpan old;
                    DateTime oldStart;
                    if (cpu.TryGetValue(pid, out old) && starts.TryGetValue(pid, out oldStart) && start == oldStart)
                    {
                        used += (elapsed - old).TotalSeconds;
                        measured = true;
                    }
                    List<int> descendants;
                    if (children.TryGetValue(pid, out descendants))
                        foreach (int child in descendants)
                            pending.Enqueue(new KeyValuePair<int, DateTime>(child, start));
                }
            }
            catch (ArgumentException)
            {
            }
            catch (InvalidOperationException)
            {
            }
            catch (System.ComponentModel.Win32Exception)
            {
            }
        }
        double now = clock.Elapsed.TotalSeconds;
        if (next.Count > 0)
            row["mas_private"] = memory / 1073741824.0;
        if (measured && now > previous)
            row["mas_cpu"] = Math.Min(100, 100 * used / ((now - previous) * Environment.ProcessorCount));
        previous = now;
        cpu = next;
        starts = newStarts;
    }
}
