/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_Notify = {
    /**
     * 是否启用通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否发送邮件
     */
    IfSendMail?: (boolean | null);
    /**
     * 收件地址
     */
    ToAddress?: (string | null);
    /**
     * 是否启用Server酱
     */
    IfServerChan?: (boolean | null);
    /**
     * Server酱密钥
     */
    ServerChanKey?: (string | null);
};

