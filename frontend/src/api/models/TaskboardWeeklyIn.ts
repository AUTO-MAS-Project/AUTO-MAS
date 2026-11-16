/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskboardWeeklyIn = {
    /**
     * 任务台游戏标识
     */
    key: string;
    /**
     * 是否标记为已完成
     */
    done: boolean;
    /**
     * 客户端看到的周键；为空时不校验客户端周键
     */
    week?: string;
};

