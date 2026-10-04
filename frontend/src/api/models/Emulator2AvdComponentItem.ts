/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdComponentItem = {
    /**
     * 组件标识: platform-tools / emulator / system-image / launcher
     */
    id: string;
    /**
     * 组件名称
     */
    name: string;
    /**
     * 固定版本
     */
    version?: string;
    /**
     * 下载大小 (字节)
     */
    sizeBytes?: number;
    /**
     * 是否已就绪
     */
    installed?: boolean;
    /**
     * 已下载的字节数 (断点续传用, 已就绪时为完整大小或 0)
     */
    downloadedBytes?: number;
    /**
     * 是否可选组件 (轻量桌面), 可选组件缺失不影响添加
     */
    optional?: boolean;
    /**
     * 许可证
     */
    license?: string;
};

