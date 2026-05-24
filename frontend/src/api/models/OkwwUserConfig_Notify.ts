/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 用户通知（复用通用字段）
 */
export type OkwwUserConfig_Notify = {
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
};

