/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CloseReason } from './CloseReason';
import type { Node } from './Node';
import type { TaskLogCursor } from './TaskLogCursor';
export type TaskLogNodesOut = {
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
    nodes?: Array<Node>;
    cursor?: (TaskLogCursor | null);
    hasMore?: boolean;
    closeReason?: (CloseReason | null);
};

