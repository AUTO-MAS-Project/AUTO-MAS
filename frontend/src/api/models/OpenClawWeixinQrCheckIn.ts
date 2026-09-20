/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 微信 Claw 二维码状态查询请求。
 */
export type OpenClawWeixinQrCheckIn = {
    /**
     * 二维码登录会话 ID
     */
    sessionId: string;
    /**
     * 微信要求时输入的配对码
     */
    verifyCode?: (string | null);
};

