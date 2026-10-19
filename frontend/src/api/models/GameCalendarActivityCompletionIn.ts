/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameCalendarActivityCompletionIn = {
    /**
     * 活动名称
     */
    name: string;
    /**
     * 活动开始时间，包含时区
     */
    startTime: string;
    /**
     * 活动结束时间，包含时区
     */
    endTime: string;
    /**
     * 是否由用户标记为已完成
     */
    completed: boolean;
    /**
     * 首页游戏标识
     */
    game: GameCalendarActivityCompletionIn.game;
    /**
     * 碧蓝档案服务器，其它游戏忽略此字段
     */
    server?: GameCalendarActivityCompletionIn.server;
};
export namespace GameCalendarActivityCompletionIn {
    /**
     * 首页游戏标识
     */
    export enum game {
        ENDFIELD = 'endfield',
        STARRAIL = 'starrail',
        GENSHIN = 'genshin',
        ZENLESS = 'zenless',
        WUTHERINGWAVES = 'wutheringwaves',
        NTE = 'nte',
        REVERSE1999 = 'reverse1999',
        BLUEARCHIVE = 'bluearchive',
        ARKNIGHTS = 'arknights',
        STELLASORA = 'stellasora',
        INFINITYNIKKI = 'infinitynikki',
    }
    /**
     * 碧蓝档案服务器，其它游戏忽略此字段
     */
    export enum server {
        CN = 'cn',
        JP = 'jp',
        GLOBAL = 'global',
    }
}

