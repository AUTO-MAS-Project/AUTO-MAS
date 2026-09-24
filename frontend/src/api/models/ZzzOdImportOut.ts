/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 导入结果：来源实例的账号字段与已启用任务编排已写入本用户，前端随后重新拉取用户数据。
 */
export type ZzzOdImportOut = {
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
     * 来源实例下标（失败为 -1）
     */
    instanceIdx: number;
    /**
     * 来源实例名称
     */
    instanceName: string;
    /**
     * 本次回填的账号字段数（仅非空值）
     */
    importedAccountCount: number;
    /**
     * 本次导入的已启用任务数
     */
    importedTaskCount: number;
    /**
     * 用户绑定槽 idx（未绑定时 -1，此时无槽内容可备份）
     */
    slot: number;
};

