/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CustomWebhook } from './CustomWebhook';
export type UserConfig_Notify = {
    /**
     * 是否启用通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否发送高资喜报
     */
    IfSendSixStar?: (boolean | null);
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
     * 用户自定义Webhook列表
     */
    CustomWebhooks?: (Array<CustomWebhook> | null);
};

