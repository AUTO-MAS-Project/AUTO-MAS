/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameTaskCancelIn = {
    /**
     * 游戏 UUID
     */
    gameId: string;
    /**
     * 期望的游戏配置版本
     */
    expectedRevision: number;
    /**
     * 期望取消的任务 UUID
     */
    expectedTaskId: string;
};

