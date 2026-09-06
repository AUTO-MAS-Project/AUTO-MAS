/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIDomainCatalogItem } from './BetterGIDomainCatalogItem';
/**
 * BetterGI 每周秘境秘境候选 + 每秘境三档奖励物
 */
export type BetterGIDomainCatalogOut = {
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
     * 秘境目录列表
     */
    data?: Array<BetterGIDomainCatalogItem>;
    /**
     * 数据来源文件绝对路径（缺省为空）
     */
    source?: (string | null);
};

