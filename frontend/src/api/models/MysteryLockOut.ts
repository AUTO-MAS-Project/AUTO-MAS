/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 重新锁定结果。
 */
export type MysteryLockOut = {
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
     * 当日是否已解锁
     */
    unlocked?: boolean;
    /**
     * 上次解锁的北京日期
     */
    unlockedDate?: string;
};

