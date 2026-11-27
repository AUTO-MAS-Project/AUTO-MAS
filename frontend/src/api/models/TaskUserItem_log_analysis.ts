/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CloseReason } from './CloseReason';
import type { Node } from './Node';
export type TaskUserItem_log_analysis = {
    /**
     * 本轮最终有效日志节点
     */
    nodes?: (Array<Node> | null);
    /**
     * 日志采集结束原因
     */
    close_reason?: (CloseReason | null);
};
