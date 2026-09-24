/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StageComboBoxItem } from './StageComboBoxItem';
export type StageComboBoxOut = {
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
     * 关卡下拉框选项
     */
    data: Array<StageComboBoxItem>;
};

