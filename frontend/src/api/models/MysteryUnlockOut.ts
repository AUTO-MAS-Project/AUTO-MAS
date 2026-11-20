/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 解锁结果。
 */
export type MysteryUnlockOut = {
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

