/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaCultivateOperatorOptionItem } from './MaaCultivateOperatorOptionItem';
export type MaaCultivateImportOut = {
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
    /**
     * 转换后的现有养成目标 JSON，不落库
     */
    targets?: string;
    /**
     * 可本地化的导入错误类型
     */
    error?: (string | null);
    /**
     * 出错条目的序号，从 1 开始
     */
    index?: (number | null);
    /**
     * 出错条目的干员名称
     */
    name?: string;
};

