/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_FunctionInput = {
    /**
     * 历史记录保留时间（天）
     */
    HistoryRetentionTime?: (7 | 15 | 30 | 60 | 90 | 180 | 365 | 0 | null);
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
     * 是否启用匿名遥测
     */
    IfEnableTelemetry?: (boolean | null);
    /**
     * 个人版 MSS 的专属编排（灾变防线），只对个人版项目生效， 普通版 MSS 与其它脚本都会忽略它。
     */
    IfPersonalMss?: (boolean | null);
    /**
     * 是否启用静默模式
     */
    IfSilence?: (boolean | null);
};

