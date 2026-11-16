/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 手动配置的回填信息，绝不返回密钥。
 */
export type OpenClawQQCredentialsOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 当前绑定版本
     */
    bindingId?: string;
    /**
     * 机器人 AppID
     */
    appId?: string;
    /**
     * 私聊接收者 OpenID，不是 QQ 号
     */
    userOpenId?: string;
    /**
     * 是否已设置 AppSecret
     */
    secretSet?: boolean;
};

