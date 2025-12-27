/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 创建 WebSocket 客户端请求
 */
export type WSClientCreateIn = {
    /**
     * 客户端名称，用于标识
     */
    name: string;
    /**
     * WebSocket 服务器地址，如 ws://localhost:5140/path
     */
    url: string;
    /**
     * 心跳发送间隔（秒）
     */
    ping_interval?: number;
    /**
     * 心跳超时时间（秒）
     */
    ping_timeout?: number;
    /**
     * 重连间隔（秒）
     */
    reconnect_interval?: number;
    /**
     * 最大重连次数，-1为无限
     */
    max_reconnect_attempts?: number;
};

