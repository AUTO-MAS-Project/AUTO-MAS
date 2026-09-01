/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWProjectUpdateData = {
    /**
     * 是否完成了一次更新检查
     */
    checked?: boolean;
    /**
     * 本次是否实际应用了更新
     */
    updated?: boolean;
    /**
     * 是否存在更新版本
     */
    updateAvailable?: boolean;
    /**
     * 更新版本是否有可安装的更新包
     */
    installable?: boolean;
    /**
     * interface 声明的当前项目版本
     */
    currentVersion?: (string | null);
    /**
     * 发现的最新项目版本
     */
    latestVersion?: (string | null);
    /**
     * 更新包来源
     */
    source?: (string | null);
};

