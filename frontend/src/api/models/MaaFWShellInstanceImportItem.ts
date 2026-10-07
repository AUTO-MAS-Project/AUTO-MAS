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
     * 是否导入成功
     */
    success?: boolean;
    /**
     * 用户 ID：建成新用户时就是它，覆盖已有用户时是那个用户
     */
    userId?: string;
    /**
     * 用户名
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

