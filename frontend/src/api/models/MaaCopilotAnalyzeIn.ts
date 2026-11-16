/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCopilotAnalyzeIn = {
    scriptId: string;
    userId: string;
    /**
     * 分析预期的森空岛绑定，账号组与角色编号组合
     */
    bindingKey?: string;
    source?: MaaCopilotAnalyzeIn.source;
    query?: string;
    /**
     * 期望覆盖有可解析要求的作业百分比
     */
    coverage?: number;
    requireModules?: boolean;
    /**
     * 忽略精英阶段已达标干员的等级差距
     */
    ignoreLevelGaps?: boolean;
};
export namespace MaaCopilotAnalyzeIn {
    export enum source {
        ALL = 'all',
        AUTHOR = 'author',
        SET = 'set',
        COPILOT = 'copilot',
    }
}

