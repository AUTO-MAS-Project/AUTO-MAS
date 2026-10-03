/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShareRiskItem } from './ShareRiskItem';
export type ShareInspectOut = {
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
     * 分享前检查出的隐私风险项
     */
    risks?: Array<ShareRiskItem>;
};

