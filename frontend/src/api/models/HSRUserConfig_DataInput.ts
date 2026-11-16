/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUserConfig_DataInput = {
    /**
     * 本周是否已完成历战余响
     */
    EchoOfWarCompletedThisWeek?: (boolean | null);
    /**
     * 历战余响最近一次完成日期
     */
    EchoOfWarLastCompletionDate?: (string | null);
    /**
     * 历战余响上次重置 ISO 周（形如 "2025-W23"）
     */
    EchoOfWarLastResetWeek?: (string | null);
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * M7A 兑换码指纹
     */
    M7ARedeemCodeFingerprint?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
    /**
     * 兑换码状态指纹（仅状态信息，不保存兑换码明文）
     */
    SRARedeemCodeFingerprint?: (string | null);
    /**
     * 本周是否已完成周常（仅依据 Data 字段判断）
     */
    WeeklyCompletedThisWeek?: (boolean | null);
    /**
     * 周常（差分宇宙/货币战争）最近一次完成日期
     */
    WeeklyLastCompletionDate?: (string | null);
    /**
     * 周常上次重置 ISO 周（形如 "2025-W23"）
     */
    WeeklyLastResetWeek?: (string | null);
};

