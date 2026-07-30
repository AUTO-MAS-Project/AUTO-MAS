/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AbyssSnapshotImportItem } from './AbyssSnapshotImportItem';
import type { HSRUserConfig } from './HSRUserConfig';
/**
 * 从 M7A config.yaml 导入三深渊快照的结果
 */
export type AbyssSnapshotImportOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 读取的 M7A config.yaml 路径
     */
    m7aConfigPath: string;
    /**
     * 三个深渊的导入结果摘要
     */
    items?: Array<AbyssSnapshotImportItem>;
    /**
     * 更新后的完整 HSR 用户配置（前端可用来同步 formData）
     */
    updatedUserData: HSRUserConfig;
};

