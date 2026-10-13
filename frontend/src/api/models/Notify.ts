/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Notify = {
    /**
     * 任务结果推送时机
     */
    send_task_result_time?: string;
    /**
     * 是否发送统计信息
     */
    if_send_statistic?: boolean;
    /**
     * 是否发送公招六星通知
     */
    if_send_six_star?: boolean;
    /**
     * 是否推送系统通知
     */
    if_push_plyer?: boolean;
    /**
     * 是否发送邮件通知
     */
    if_send_mail?: boolean;
    /**
     * 是否启用Koishi支持
     */
    if_koishi_support?: boolean;
    /**
     * Koishi服务器地址
     */
    koishi_server_address?: string;
    /**
     * Koishi Token
     */
    koishi_token?: string;
    /**
     * 是否启用 QQ 官方机器人通知
     */
    if_openclaw_qq?: boolean;
    /**
     * QQ 官方机器人 App ID
     */
    openclaw_qq_app_id?: string;
    /**
     * QQ 官方机器人客户端密钥
     */
    openclaw_qq_client_secret?: string;
    /**
     * QQ 官方机器人目标用户 OpenID
     */
    openclaw_qq_target_open_id?: string;
    /**
     * SMTP服务器地址
     */
    smtp_server_address?: string;
    /**
     * SMTP授权码
     */
    authorization_code?: string;
    /**
     * 邮件发送地址
     */
    from_address?: string;
    /**
     * 邮件接收地址
     */
    to_address?: string;
    /**
     * 是否使用ServerChan推送
     */
    if_server_chan?: boolean;
    /**
     * ServerChan推送密钥
     */
    server_chan_key?: string;
    /**
     * 测试通知（写 True 触发一次）
     */
    test?: boolean;
};

