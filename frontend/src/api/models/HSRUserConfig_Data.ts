/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUserConfig_Data = {
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
    /**
     * 是否通过检查
     */
    IfPassCheck?: (boolean | null);
    /**
     * 本周是否已完成历战余响
     */
    EchoOfWarCompletedThisWeek?: (boolean | null);
    /**
     * 历战余响上次重置 ISO 周（形如 2025-W23）
     */
    EchoOfWarLastResetWeek?: (string | null);
    /**
     * 历战余响最近一次完成日期
     */
    EchoOfWarLastCompletionDate?: (string | null);
    /**
     * 周常最近一次完成日期
     */
    WeeklyLastCompletionDate?: (string | null);
    /**
     * 本周是否已完成周常
     */
    WeeklyCompletedThisWeek?: (boolean | null);
    /**
     * 周常上次重置 ISO 周（形如 2025-W23）
     */
    WeeklyLastResetWeek?: (string | null);
    /**
     * 本月是否已完成三深渊
     */
    AbyssCompletedThisMonth?: (boolean | null);
    /**
     * 三深渊上次重置自然月（形如 2025-06）
     */
    AbyssLastResetMonth?: (string | null);
    /**
     * 三深渊最近一次完成日期
     */
    AbyssLastCompletionDate?: (string | null);
};

