/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskCreateIn = {
    /**
     * 目标任务ID, 设置类任务可选对应托管ID或账号ID, 代理类任务可选对应队列ID或托管ID
     */
    taskId: string;
    /**
     * 任务模式; CycleRun 为循环运行, 仅接受循环队列, 其托管按 AutoProxy 执行
     */
    mode: TaskCreateIn.mode;
    /**
     * 可选：仅对队列任务生效；从指定托管ID开始执行（之前的托管将被标记为跳过）
     */
    resumeFromScriptId?: (string | null);
    /**
     * 可选：仅对托管的自动代理任务生效；只运行该托管下的这一个账号
     */
    userId?: (string | null);
    /**
     * 可选：仅对托管的自动代理任务生效；只运行指定的多个账号
     */
    userIds?: (Array<string> | null);
    /**
     * 可选：仅对队列任务生效；按托管ID指定本次要运行的账号；未列出的托管不限, 空列表表示该托管本次整项跳过
     */
    queueUserIds?: (Record<string, Array<string>> | null);
    /**
     * 可选：仅 ScriptConfig 生效；只读查看会话（不注入基线、不回读字段），用于预览历史备份
     */
    viewOnly?: boolean;
    /**
     * 可选：仅 ScriptConfig 生效；直控指定会话窗口打开的原生实例（临时切换活跃，会话结束还原）
     */
    instanceIdx?: (number | null);
};
export namespace TaskCreateIn {
    /**
     * 任务模式; CycleRun 为循环运行, 仅接受循环队列, 其托管按 AutoProxy 执行
     */
    export enum mode {
        AUTO_PROXY = 'AutoProxy',
        SCRIPT_CONFIG = 'ScriptConfig',
        UPDATE = 'Update',
        CYCLE_RUN = 'CycleRun',
    }
}

