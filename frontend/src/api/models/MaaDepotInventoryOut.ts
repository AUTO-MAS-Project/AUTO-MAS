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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 库存选项（label=数量字符串，value=物品ID）
     */
    data: Array<ComboBoxItem>;
    /**
     * 最近识别时间（本地 ISO 格式）；无法确定识别时间时为 None
     */
    recognizedAt?: (string | null);
};

