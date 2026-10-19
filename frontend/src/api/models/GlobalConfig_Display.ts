/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Display = {
    /**
     * 无人值守时是否允许 MAS 挂载虚拟显示器。 所有真实显示输出都断开后 Windows 只保留一块占位的幻影屏，它照旧上报正常的 分辨率但背后没有输出；冷启动时更会起在很小的分辨率上，把被托管的 PC 端游戏 窗口压小并被游戏写进自己的配置，之后每轮都在同一处失败。挂一块真实的虚拟屏 可从源头断掉。 需要用户自行安装 Parsec 虚拟显示驱动，MAS 不分发驱动。
     */
    IfEnableVirtualDisplay?: (boolean | null);
    /**
     * 虚拟显示器的刷新率（分辨率固定 1920x1080）。 分辨率固定是因为只有它 Windows 给 100% 缩放，再高会被自动上缩放，游戏窗口 又要面对 DPI 虚拟化。取值必须在驱动 advertise 的模式表里，否则会被 BADMODE 拒绝。
     */
    VirtualDisplayMode?: ('1920x1080@60' | '1920x1080@30' | null);
};

