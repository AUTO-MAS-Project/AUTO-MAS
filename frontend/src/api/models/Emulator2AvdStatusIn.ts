/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdStatusIn = {
    /**
     * 魔改 AVD 根目录 (解压好的模拟器内测包)
     */
    root: string;
    /**
     * 跳过硬件加速与 Vulkan 检查的缓存重新查; 用户点「检查」时传 true
     */
    refresh?: boolean;
};

