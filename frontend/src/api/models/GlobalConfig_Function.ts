/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Function = {
    /**
     * 历史记录保留时间（天）
     */
    HistoryRetentionTime?: (7 | 15 | 30 | 60 | 90 | 180 | 365 | 0 | null);
    /**
     * 历史记录页同一天内记录条目的顺序：desc 最新在前，asc 最早在前
     */
    HistoryOrder?: ('desc' | 'asc' | null);
    /**
     * 是否同意 Bilibili 协议
     */
    IfAgreeBilibili?: (boolean | null);
    /**
     * 是否允许睡眠
     */
    IfAllowSleep?: (boolean | null);
    /**
     * 是否屏蔽模拟器广告
     */
    IfBlockAd?: (boolean | null);
    /**
     * 启动时是否启用 MCP 服务，重启后生效
     */
    IfEnableMCP?: (boolean | null);
    /**
     * 是否启用匿名遥测
     */
    IfEnableTelemetry?: (boolean | null);
    /**
     * 是否启用静默模式
     */
    IfSilence?: (boolean | null);
};

