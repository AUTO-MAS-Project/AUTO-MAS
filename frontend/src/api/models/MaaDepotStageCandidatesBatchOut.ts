/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
export type MaaDepotStageCandidatesBatchOut = {
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
    /**
     * 按物品ID分组的候选关卡，未找到候选时为空列表
     */
    data?: Record<string, Array<ComboBoxItem>>;
};

