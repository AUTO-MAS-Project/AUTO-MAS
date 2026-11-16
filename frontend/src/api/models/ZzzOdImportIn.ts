/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 基于一条龙已有实例快速生成当前账号配置（覆盖本账号账号与任务编排）。
 */
export type ZzzOdImportIn = {
    /**
     * 所属托管ID
     */
    scriptId: string;
    /**
     * 目标账号ID（独立的账号级配置）
     */
    userId: string;
    /**
     * 来源母版实例下标（读取该实例的账号信息与已启用任务编排）
     */
    instanceIdx: number;
};

