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
     * 已就绪时为实际装着的版本 (source.properties), 未就绪时为要下载的固定版本
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
    /**
     * 是否取自 mas-avd.json 的 sdkRoot 指定的本地 SDK (不经下载器, 没有下载大小可言)
     */
    localSdk?: boolean;
    /**
     * 仅 Android 模拟器: 根目录里是魔改 AVD 内测包的自编版, 已就绪
     */
    testPackage?: boolean;
    /**
     * 仅 Android 模拟器: 根目录里没有模拟器或不是自编版; 模拟器不下载, 要把魔改 AVD 内测包解压到根目录
     */
    needsTestPackage?: boolean;
};

