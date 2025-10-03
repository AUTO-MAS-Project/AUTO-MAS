/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Notify = {
    /**
     * 任务结果推送时机
     */
    SendTaskResultTime?: ('不推送' | '任何时刻' | '仅失败时' | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否发送公招六星通知
     */
    IfSendSixStar?: (boolean | null);
    /**
     * 是否推送系统通知
     */
    IfPushPlyer?: (boolean | null);
    /**
     * 是否发送邮件通知
     */
    IfSendMail?: (boolean | null);
    /**
     * SMTP服务器地址
     */
    SMTPServerAddress?: (string | null);
    /**
     * SMTP授权码
     */
    AuthorizationCode?: (string | null);
    /**
     * 邮件发送地址
     */
    FromAddress?: (string | null);
    /**
     * 邮件接收地址
     */
    ToAddress?: (string | null);
    /**
     * 是否使用ServerChan推送
     */
    IfServerChan?: (boolean | null);
    /**
     * ServerChan推送密钥
     */
    ServerChanKey?: (string | null);
};

