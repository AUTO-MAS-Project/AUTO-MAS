/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 日常活动中的单项任务。
 */
export type CommunityActivityTaskOut = {
    /**
     * 任务名称
     */
    name: string;
    /**
     * 已完成数量
     */
    completed: number;
    /**
     * 目标数量
     */
    target: number;
    /**
     * 任务状态
     */
    status: string;
    /**
     * 任务周期
     */
    period?: string;
};

