/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 发送认证请求
 */
export type WSClientAuthIn = {
    /**
     * 客户端名称
     */
    name: string;
    /**
     * 认证 Token
     */
    token: string;
    /**
     * 认证消息类型
     */
    auth_type?: string;
    /**
     * 额外认证数据
     */
    extra_data?: (Record<string, any> | null);
};

