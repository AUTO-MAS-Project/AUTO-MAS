/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 塔吉多一次性账号密码登录请求。
 */
export type TaygedoLoginIn = {
    /**
     * 账号组 UUID
     */
    accountId: string;
    /**
     * 塔吉多账号或手机号
     */
    phone: string;
    /**
     * 塔吉多账号密码
     */
    password: string;
};

