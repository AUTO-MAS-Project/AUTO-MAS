/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWProjectUpdateData = {
    /**
     * 是否完成更新检查
     */
    checked: boolean;
    /**
     * 是否实际更新了 MaaFW 项目资源
     */
    updated: boolean;
    /**
     * 是否发现新版本
     */
    updateAvailable?: boolean;
    /**
     * 发现的新版本是否有可安装包
     */
    installable?: boolean;
    /**
     * 更新前的项目版本
     */
    currentVersion: string;
    /**
     * 最新项目版本
     */
    latestVersion?: (string | null);
    /**
     * 实际使用的更新源
     */
    source?: (string | null);
    /**
     * 更新源返回的原始错误码（例如 MirrorChyan CDK 错误码）
     */
    providerErrorCode?: (number | null);
    /**
     * 项目更新日志
     */
    logs?: Array<string>;
};

