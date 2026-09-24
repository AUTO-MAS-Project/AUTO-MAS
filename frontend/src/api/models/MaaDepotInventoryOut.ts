/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
export type MaaDepotInventoryOut = {
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
     * 库存选项（label=数量字符串，value=物品ID）
     */
    data: Array<ComboBoxItem>;
    /**
     * 最近识别时间（本地 ISO 格式）；无法确定识别时间时为 None
     */
    recognizedAt?: (string | null);
};

