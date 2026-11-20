using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// DXGI 与 GPU Engine 计数器用同一 LUID 匹配。LUID 只留在探针内。
sealed class Adapters
{
    [DllImport("dxgi.dll")]
    static extern int CreateDXGIFactory1(ref Guid iid, out IntPtr factory);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int Enumerate(IntPtr factory, uint index, out IntPtr adapter);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int Describe(IntPtr adapter, out Description description);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct Description
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string Name;
        public uint Vendor, Device, Subsystem, Revision;
        public UIntPtr Dedicated, System, Shared;
        public uint Low, High, Flags;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Open
    {
        public uint Low, High, Handle;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct Query
    {
        public uint Handle, Type;
        public IntPtr Data;
        public uint Size;
    }
    [DllImport("gdi32.dll")]
    static extern int D3DKMTOpenAdapterFromLuid(ref Open open);
    [DllImport("gdi32.dll")]
    static extern int D3DKMTQueryAdapterInfo(ref Query query);
    [DllImport("gdi32.dll")]
    static extern int D3DKMTCloseAdapter(ref uint handle);
    static int Flags(Description d)
    {
        var open = new Open { Low = d.Low, High = d.High };
        if (D3DKMTOpenAdapterFromLuid(ref open) != 0)
            return 0;
        IntPtr data = Marshal.AllocHGlobal(4);
        try
        {
            var q = new Query { Handle = open.Handle, Type = 15, Data = data, Size = 4 };
            return D3DKMTQueryAdapterInfo(ref q) == 0 ? Marshal.ReadInt32(data) : 0;
        }
        finally
        {
            Marshal.FreeHGlobal(data);
            D3DKMTCloseAdapter(ref open.Handle);
        }
    }
    [DllImport("dxcore.dll")]
    static extern int DXCoreCreateAdapterFactory(ref Guid iid, out IntPtr factory);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int ByLuid(IntPtr factory, ref ulong luid, ref Guid iid, out IntPtr adapter);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int Property(IntPtr adapter, uint property, UIntPtr size, out byte result);

    // DXCore 的 IsIntegrated 也适用于只有一张核显、没有混合显卡标志的电脑。
    static string Integrated(Description d)
    {
        IntPtr factory = IntPtr.Zero, adapter = IntPtr.Zero;
        try
        {
            var fid = new Guid("78ee5945-c36e-4b13-a669-005dd11c0f06");
            if (DXCoreCreateAdapterFactory(ref fid, out factory) != 0)
                return "unknown";
            var aid = new Guid("f0db4c7f-fe5a-42a2-bd62-f2a6cf6fc83e");
            ulong luid = ((ulong)d.High << 32) | d.Low;
            var find = (ByLuid)Marshal.GetDelegateForFunctionPointer(
                Marshal.ReadIntPtr(Marshal.ReadIntPtr(factory), 4 * IntPtr.Size), typeof(ByLuid));
            if (find(factory, ref luid, ref aid, out adapter) != 0)
                return "unknown";
            var get = (Property)Marshal.GetDelegateForFunctionPointer(
                Marshal.ReadIntPtr(Marshal.ReadIntPtr(adapter), 6 * IntPtr.Size), typeof(Property));
            byte integrated;
            if (get(adapter, 12, (UIntPtr)1, out integrated) != 0)
                return "unknown";
            return integrated == 0 ? "discrete" : "integrated";
        }
        catch (DllNotFoundException)
        {
            return "unknown";
        }
        catch (EntryPointNotFoundException)
        {
            return "unknown";
        }
        finally
        {
            if (adapter != IntPtr.Zero)
                Marshal.Release(adapter);
            if (factory != IntPtr.Zero)
                Marshal.Release(factory);
        }
    }
    bool enumerated, software;
    sealed class Card
    {
        public string Id, Name, Kind;
        public double Vram;
    }
    readonly List<Card> cards = new List<Card>();

    public Adapters()
    {
        // IDXGIFactory1::EnumAdapters1 与 IDXGIAdapter1::GetDesc1 的固定 COM 槽。
        var iid = new Guid("770aae78-f26f-4dba-a829-253c83d1b387");
        IntPtr fac;
        if (CreateDXGIFactory1(ref iid, out fac) != 0)
            return;
        try
        {
            var next = (Enumerate)Marshal.GetDelegateForFunctionPointer(
                Marshal.ReadIntPtr(Marshal.ReadIntPtr(fac), 12 * IntPtr.Size), typeof(Enumerate));
            IntPtr a;
            for (uint i = 0; i < 32; i++)
            {
                int hr = next(fac, i, out a);
                if (hr != 0)
                {
                    enumerated = hr == unchecked((int)0x887A0002);
                    break;
                }
                try
                {
                    var describe = (Describe)Marshal.GetDelegateForFunctionPointer(
                        Marshal.ReadIntPtr(Marshal.ReadIntPtr(a), 10 * IntPtr.Size), typeof(Describe));
                    Description d;
                    if (describe(a, out d) != 0)
                        return;
                    if ((d.Flags & 2) != 0)
                    {
                        software = true;
                        continue;
                    }
                    if ((d.Flags & 1) != 0)
                        continue;
                    int f = Flags(d);
                    if ((f & (4 | 64 | 128)) != 0)
                        continue;
                    string kind = (f & 32) != 0 ? "integrated" : (f & 16) != 0 ? "discrete" : Integrated(d);
                    cards.Add(new Card { Id = "luid_0x" + d.High.ToString("x8") + "_0x" + d.Low.ToString("x8") + "_",
                                         Name = d.Name, Kind = kind, Vram = d.Dedicated.ToUInt64() / 1073741824.0 });
                }
                finally
                {
                    Marshal.Release(a);
                }
            }
        }
        finally
        {
            Marshal.Release(fac);
        }
    }
    public void Sample(Dictionary<string, object> row, Counters counters)
    {
        if (enumerated)
        {
            row["gpu_count"] = cards.Count;
            if (cards.Count == 0)
                row["graphics_layout"] = software ? "software-only" : "no-adapter";
            else if (cards.TrueForAll(c => c.Kind == "integrated"))
                row["graphics_layout"] = "integrated-only";
            else if (cards.TrueForAll(c => c.Kind == "discrete"))
                row["graphics_layout"] = "discrete-only";
            else if (cards.Exists(c => c.Kind == "integrated") && cards.Exists(c => c.Kind == "discrete"))
                row["graphics_layout"] = "mixed";
        }

        var engines = counters.Read("gpu");
        var dedicated = counters.Read("dedicated");
        var shared = counters.Read("shared");
        for (int index = 0; index < Math.Min(4, cards.Count); index++)
        {
            var card = cards[index];
            string prefix = "gpu" + index + "_";
            row[prefix + "series"] = card.Name;
            row[prefix + "kind"] = card.Kind;
            row[prefix + "vram"] = card.Vram;
            var sums = new Dictionary<string, double>();
            foreach (var engine in engines)
            {
                int start = engine.Key.IndexOf(card.Id, StringComparison.OrdinalIgnoreCase);
                if (start < 0)
                    continue;
                string key = engine.Key.Substring(start);
                double value;
                sums.TryGetValue(key, out value);
                sums[key] = value + engine.Value;
            }
            foreach (double value in sums.Values)
            {
                object peak;
                if (!row.TryGetValue(prefix + "busy", out peak) || (double)peak < value)
                    row[prefix + "busy"] = Math.Min(100, value);
            }
            foreach (var usage in dedicated)
                if (usage.Key.IndexOf(card.Id, StringComparison.OrdinalIgnoreCase) >= 0)
                    row[prefix + "dedicated"] = usage.Value / 1073741824;
            foreach (var usage in shared)
                if (usage.Key.IndexOf(card.Id, StringComparison.OrdinalIgnoreCase) >= 0)
                    row[prefix + "shared"] = usage.Value / 1073741824;
        }
    }
}
