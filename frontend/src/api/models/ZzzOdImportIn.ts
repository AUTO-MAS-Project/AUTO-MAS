/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 基于一条龙已有实例快速生成当前用户配置（覆盖本用户账号与任务编排）。
 */
export type ZzzOdImportIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标用户ID（独立的用户级配置）
     */
    userId: string;
    /**
     * 来源母版实例下标（读取该实例的账号信息与已启用任务编排）
     */
    instanceIdx: number;
};

