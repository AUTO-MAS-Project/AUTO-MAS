/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 单独通知（在通用字段上增加掉落统计开关）
 */
export type BetterGIUserConfig_Notify = {
    /**
     * 是否启用通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否发送邮件通知
     */
    IfSendMail?: (boolean | null);
    /**
     * 邮件接收地址
     */
    ToAddress?: (string | null);
    /**
     * 是否使用Server酱推送
     */
    IfServerChan?: (boolean | null);
    /**
     * ServerChanKey
     */
    ServerChanKey?: (string | null);
    /**
     * 是否统计掉落（BGI「奖励识别」汇总，默认开启）
     */
    IfSendDropStatistics?: (boolean | null);
};

