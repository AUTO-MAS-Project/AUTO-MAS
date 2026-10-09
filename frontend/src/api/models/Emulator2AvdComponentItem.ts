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
     * 装着的版本; 没装为空
     */
    version?: string;
    /**
     * 是否已就绪
     */
    installed?: boolean;
    /**
     * 是否可选组件 (轻量桌面), 可选组件缺失不影响添加
     */
    optional?: boolean;
    /**
     * 是否取自 mas-avd.json 的 sdkRoot 指定的本地 SDK
     */
    localSdk?: boolean;
    /**
     * 仅 Android 模拟器: 根目录里是魔改 AVD 内测包的自编版, 已就绪
     */
    testPackage?: boolean;
    /**
     * 仅 Android 模拟器: 根目录里没有模拟器、不是自编版或内测包太旧
     */
    needsTestPackage?: boolean;
    /**
     * 仅 Android 模拟器: 内测包编号 (source.properties 的 Pkg.BuildId, 如 mas-19); 不是自编版或读不到为 null
     */
    build?: (string | null);
    /**
     * 仅 Android 模拟器: 是自编版, 但内测包编号低于最低要求或读不到, 要换新包
     */
    outdatedTestPackage?: boolean;
};

