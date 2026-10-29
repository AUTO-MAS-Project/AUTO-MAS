/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 手动替换机器人凭据。
 */
export type OpenClawQQCredentialsIn = {
    /**
     * 读取配置时返回的绑定版本
     */
    bindingId: string;
    /**
     * 机器人 AppID
     */
    appId: string;
    userOpenId: string;
    /**
     * 新 AppSecret；省略时仅允许同一 AppID 保留原密钥
     */
    clientSecret?: (string | null);
};

