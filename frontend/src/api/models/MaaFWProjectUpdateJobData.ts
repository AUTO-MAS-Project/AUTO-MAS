/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWProjectUpdateJobResult } from './MaaFWProjectUpdateJobResult';
import type { WSMaaFWProjectUpdateProgressData } from './WSMaaFWProjectUpdateProgressData';
/**
 * 该脚本当前或最近一次手动更新（apply）。只在后端进程内保留：下一次手动更新开始
 * 或后端重启即被替换 / 清空。
 */
export type MaaFWProjectUpdateJobData = {
    /**
     * idle 本次后端启动以来没有手动更新；running 正在更新；finished 已结束
     */
    state?: MaaFWProjectUpdateJobData.state;
    /**
     * 这次手动更新的唯一作业 ID；idle 时为空
     */
    jobId?: (string | null);
    /**
     * 开始时间（ISO 8601）
     */
    startedAt?: (string | null);
    /**
     * 结束时间（ISO 8601）；进行中为空
     */
    finishedAt?: (string | null);
    /**
     * 已推送过的进度事件（与 WS maafw.project-update.progress 同一结构），按顺序重放即可还原更新过程面板；同阶段连续的进度只留最新一条，日志行只留最近的
     */
    events?: Array<WSMaaFWProjectUpdateProgressData>;
    /**
     * 结束后的结果；进行中为空
     */
    result?: (MaaFWProjectUpdateJobResult | null);
};
export namespace MaaFWProjectUpdateJobData {
    /**
     * idle 本次后端启动以来没有手动更新；running 正在更新；finished 已结束
     */
    export enum state {
        IDLE = 'idle',
        RUNNING = 'running',
        FINISHED = 'finished',
    }
}

