/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
export type MaaEndOptionsOut = {
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
     * MaaEnd 控制器选项
     */
    controllers: Array<ComboBoxItem>;
    /**
     * 控制器协议类型映射
     */
    controllerTypes: Record<string, string>;
    /**
     * MaaEnd 基质刷取地点选项
     */
    essenceLocations: Array<ComboBoxItem>;
};

