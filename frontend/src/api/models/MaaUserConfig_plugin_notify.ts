/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaUserConfig_plugin_notify = {
    /**
     * 是否启用用户通知
     */
    enabled?: (boolean | null);
    /**
     * 是否发送统计信息
     */
    if_send_statistic?: (boolean | null);
    /**
     * 是否发送六星通知
     */
    if_send_six_star?: (boolean | null);
    /**
     * 是否发送邮件通知
     */
    if_send_mail?: (boolean | null);
    /**
     * 邮件接收地址
     */
    to_address?: (string | null);
    /**
     * 是否启用 Server 酱
     */
    if_server_chan?: (boolean | null);
    /**
     * Server 酱推送密钥
     */
    server_chan_key?: (string | null);
};

