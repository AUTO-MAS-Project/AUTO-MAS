/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WhimboxUserConfig_Notify = {
    /**
     * 是否启用账号通知
     */
    Enabled?: (boolean | null);
    /**
     * 是否发送邮件
     */
    IfSendMail?: (boolean | null);
    /**
     * 是否发送账号统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否启用 Server 酱
     */
    IfServerChan?: (boolean | null);
    /**
     * Server 酱密钥
     */
    ServerChanKey?: (string | null);
    /**
     * 账号通知收件地址
     */
    ToAddress?: (string | null);
};

