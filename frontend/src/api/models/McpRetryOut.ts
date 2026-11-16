/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { McpStatusData } from './McpStatusData';
export type McpRetryOut = {
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
    data: McpStatusData;
    /**
     * 仅表示已受理加载，成功以 data.state=ready 为准
     */
    accepted: boolean;
};

