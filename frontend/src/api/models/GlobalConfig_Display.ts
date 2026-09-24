/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Display = {
    /**
     * 无人值守时，检测不到任何真实显示输出则临时挂载虚拟显示器（需自行安装 Parsec 虚拟显示驱动）
     */
    IfEnableVirtualDisplay?: (boolean | null);
    /**
     * 虚拟显示器的刷新率，分辨率固定 1920x1080；形如 1920x1080@60
     */
    VirtualDisplayMode?: (string | null);
};

