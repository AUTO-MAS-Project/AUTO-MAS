/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWShellInstanceImportItem = {
    /**
     * 实例 ID
     */
    instanceId: string;
    /**
     * 外壳里的实例名
     */
    instanceName?: string;
    /**
     * 是否建成了用户
     */
    success?: boolean;
    /**
     * 新用户 ID（失败时为空）
     */
    userId?: string;
    /**
     * 新用户名
     */
    name?: string;
    /**
     * 导入进队列的任务数
     */
    importedTaskCount?: number;
    /**
     * 当前项目里对不上、没导入的任务 / 选项 / 取值
     */
    skipped?: Array<string>;
    /**
     * 失败原因（成功时为空）
     */
    error?: string;
};

