/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Notify = {
    /**
     * 邮箱授权码
     */
    AuthorizationCode?: (string | null);
    /**
     * 中国移动新消息 Channel API Key
     */
    CMCCNewMsgApiKey?: (string | null);
    /**
     * 发件地址
     */
    FromAddress?: (string | null);
    /**
     * 是否启用中国移动新消息通知
     */
    IfCMCCNewMsg?: (boolean | null);
    /**
     * 是否发送Koishi通知
     */
    IfKoishiSupport?: (boolean | null);
    /**
     * 是否启用 QQ 官方机器人通知（凭据由扫码登录流程管理）
     */
    IfOpenClawQQ?: (boolean | null);
    /**
     * 是否推送系统通知
     */
    IfPushPlyer?: (boolean | null);
    /**
     * 是否发送邮件
     */
    IfSendMail?: (boolean | null);
    /**
     * 是否发送六星通知
     */
    IfSendSixStar?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    IfSendStatistic?: (boolean | null);
    /**
     * 是否启用 Server 酱
     */
    IfServerChan?: (boolean | null);
    /**
     * Koishi WebSocket 服务器地址
     */
    KoishiServerAddress?: (string | null);
    /**
     * Koishi Token
     */
    KoishiToken?: (string | null);
    /**
     * SMTP 服务器地址
     */
    SMTPServerAddress?: (string | null);
    /**
     * 任务结果推送时间
     */
    SendTaskResultTime?: ('不推送' | '任何时刻' | '仅失败时' | null);
    /**
     * Server 酱密钥
     */
    ServerChanKey?: (string | null);
    /**
     * 收件地址
     */
    ToAddress?: (string | null);
};

