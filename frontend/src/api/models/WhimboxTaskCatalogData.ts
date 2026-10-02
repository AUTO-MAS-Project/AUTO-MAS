/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WhimboxOptionCatalogItem } from './WhimboxOptionCatalogItem';
import type { WhimboxTaskCatalogItem } from './WhimboxTaskCatalogItem';
/**
 * 任务目录数据：步骤开关 + 参数字段 + 上游版本提示
 */
export type WhimboxTaskCatalogData = {
    /**
     * 一条龙步骤开关（键集与顺序来自上游模板）
     */
    steps?: Array<WhimboxTaskCatalogItem>;
    /**
     * 一条龙目标/参数字段
     */
    options?: Array<WhimboxOptionCatalogItem>;
    /**
     * 奇想盒后端版本（dist-info）
     */
    upstream_version?: string;
};

