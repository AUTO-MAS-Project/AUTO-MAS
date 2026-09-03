/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskCreateIn = {
    /**
     * 目标任务ID, 设置类任务可选对应脚本ID或用户ID, 代理类任务可选对应队列ID或脚本ID
     */
    taskId: string;
    /**
     * 任务模式; CycleRun 为循环运行, 仅接受循环队列, 其脚本按 AutoProxy 执行
     */
    mode: TaskCreateIn.mode;
    /**
     * 可选：仅对队列任务生效；从指定脚本ID开始执行（之前的脚本将被标记为跳过）
     */
    resumeFromScriptId?: (string | null);
    /**
     * 可选：仅对脚本的自动代理任务生效；只运行该脚本下的这一个用户
     */
    userId?: (string | null);
};
export namespace TaskCreateIn {
    /**
     * 任务模式; CycleRun 为循环运行, 仅接受循环队列, 其脚本按 AutoProxy 执行
     */
    export enum mode {
        AUTO_PROXY = 'AutoProxy',
        SCRIPT_CONFIG = 'ScriptConfig',
        UPDATE = 'Update',
        CYCLE_RUN = 'CycleRun',
    }
}

