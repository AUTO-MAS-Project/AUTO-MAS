/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkScriptTaskItem = {
    /**
     * 任务 ID（项目任务列表里的「模块.类名」）
     */
    taskId: string;
    /**
     * 任务序号，即启动参数 -t 的值（从 1 开始）
     */
    index: number;
    /**
     * 任务显示名
     */
    name: string;
    /**
     * 是否为持续触发任务（不会自行结束，暂不支持运行）
     */
    continuous: boolean;
};

