/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWEmbeddedProjection = {
    /**
     * 来源目录字节数
     */
    sourceSizeBytes?: number;
    /**
     * 副本字节数
     */
    payloadSizeBytes?: number;
    /**
     * 省下的字节数
     */
    savedBytes?: number;
    /**
     * 省下的比例
     */
    savedPercent?: number;
    /**
     * 排除的路径数
     */
    excludedCount?: number;
    /**
     * 排除路径与原因（最多 128 条）
     */
    excludedReasons?: Record<string, string>;
    /**
     * 排除清单是否被截断
     */
    excludedTruncated?: boolean;
    /**
     * 移除的外壳家族
     */
    shellFamilies?: Array<string>;
    /**
     * 是否退回保守模式
     */
    conservative?: boolean;
    /**
     * 投影警告
     */
    warnings?: Array<string>;
    /**
     * 来源自带 MaaFramework 的版本（PEP 440），运行池按它钉运行时
     */
    bundledMaaFWVersion?: string;
};

