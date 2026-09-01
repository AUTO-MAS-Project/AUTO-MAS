/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 库街区短信验证码登录请求。
 */
export type KuroSmsLoginIn = {
    /**
     * 账号组 UUID
     */
    accountId: string;
    /**
     * 发送验证码返回的短期会话标识
     */
    sessionId: string;
    /**
     * 库街区手机号
     */
    phone: string;
    /**
     * 短信验证码
     */
    code: string;
};
