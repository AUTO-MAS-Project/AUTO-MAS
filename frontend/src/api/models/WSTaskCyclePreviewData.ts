/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 循环运行的一个待运行条目。
 */
export type WSTaskCyclePreviewData = {
    /**
     * 队列项 ID
     */
    queueItemId: string;
    /**
     * 脚本 ID
     */
    scriptId: string;
    /**
     * 脚本名称
     */
    scriptName: string;
    /**
     * 下次运行时间, 格式为YYYY-MM-DD HH:MM:SS
     */
    nextRunAt: string;
    /**
     * 是否已到运行时间
     */
    isDue?: boolean;
    /**
     * 是否正在运行
     */
    isRunning?: boolean;
};
