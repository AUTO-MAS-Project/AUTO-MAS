/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2SearchItem = {
    /**
     * 模拟器类型
     */
    type: string;
    /**
     * 探测到的版本号
     */
    version?: string;
    /**
     * 安装目录
     */
    installPath: string;
    /**
     * 安装别名, 默认取目录名
     */
    alias?: string;
    /**
     * 能否加入 Emulator 2.0
     */
    supported: boolean;
    /**
     * 判定原因: ok 可添加 / version_too_old 版本太旧 / planned 后续版本接入 / unsupported 暂不支持 / already_added 已添加 / not_found 找不到模拟器程序 / probe_failed 版本认不出 / components_missing 魔改 AVD 根目录里组件不全 (要用完整的模拟器内测包) / test_package_required 根目录里的模拟器不是魔改 AVD 内测包里的自编版 / test_package_outdated 魔改 AVD 内测包编号太旧或读不到, 要换新包
     */
    reason: string;
    /**
     * 实例数量
     */
    instanceCount?: (number | null);
};

