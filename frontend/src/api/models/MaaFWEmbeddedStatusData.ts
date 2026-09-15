/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWEmbeddedProjection } from './MaaFWEmbeddedProjection';
export type MaaFWEmbeddedStatusData = {
    /**
     * 是否内嵌
     */
    enabled?: boolean;
    /**
     * 副本目录（只读展示）
     */
    copyPath?: string;
    /**
     * 副本是否完整
     */
    copyHealthy?: boolean;
    /**
     * 来源目录（Info.Path）
     */
    sourcePath?: string;
    /**
     * 来源目录是否还在
     */
    sourceExists?: boolean;
    /**
     * 导入时来源的 interface 版本
     */
    sourceVersion?: string;
    /**
     * 导入时间
     */
    importedAt?: string;
    /**
     * 投影报告
     */
    report?: (MaaFWEmbeddedProjection | null);
};

