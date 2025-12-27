/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 发送自定义 JSON 消息请求
 */
export type WSClientSendJsonIn = {
    /**
     * 客户端名称
     */
    name: string;
    /**
     * 消息 ID
     */
    msg_id?: string;
    /**
     * 消息类型
     */
    msg_type: string;
    /**
     * 消息数据
     */
    data?: Record<string, any>;
};

