/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaCultivateOperatorOptionItem } from './MaaCultivateOperatorOptionItem';
export type MaaCultivateOperatorsOut = {
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
     * 干员目录（含目标编辑用名称目录）
     */
    data?: Array<MaaCultivateOperatorOptionItem>;
};

