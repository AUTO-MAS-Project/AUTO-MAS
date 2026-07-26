/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 前端协商主 WebSocket 链接时使用的元信息。
 */
export type WebSocketMetaOut = {
    /**
     * 后端当前是否处于开发模式
     */
    devMode: boolean;
    /**
     * 主 WebSocket 路径
     */
    wsPath?: string;
    /**
     * 仅向可信本地 Electron/开发前端返回的短期握手令牌
     */
    wsAuthToken?: (string | null);
};

