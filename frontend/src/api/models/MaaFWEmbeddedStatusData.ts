/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWEmbeddedProjection } from './MaaFWEmbeddedProjection';
export type MaaFWEmbeddedStatusData = {
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
     * 来源目录是否还在；导入完成后来源可以删，不在只是不能重新导入
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
    /**
     * 跟随来源目录（开发者模式）下视图上次从来源目录同步的时间；没同步过为空
     */
    followSourceSyncedAt?: string;
    /**
     * 项目按源码形态导入（interface 在 assets/、Agent 在源码目录）：始终跟随来源目录，不做项目更新
     */
    sourceForm?: boolean;
};

