/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 用户正在跑的任务进度（目前只有 MFW 给）。
 */
export type WSTaskUserProgressData = {
    /**
     * 当前是第几个任务, 从 1 起
     */
    current: number;
    /**
     * 本次共几个任务
     */
    total: number;
    /**
     * 当前任务名
     */
    task: string;
};

