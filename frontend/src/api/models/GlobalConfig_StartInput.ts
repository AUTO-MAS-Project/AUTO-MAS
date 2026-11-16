/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_StartInput = {
    /**
     * 是否在定时队列前五分钟唤醒电脑
     */
    IfScheduledWakeUp?: (boolean | null);
    /**
     * 是否在开机自启或定时唤醒启动时静默进入托盘
     */
    IfMinimizeDirectly?: (boolean | null);
    /**
     * 是否自动启动
     */
    IfSelfStart?: (boolean | null);
};

