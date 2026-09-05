/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 每周秘境可选秘境目录项（来源：产出表或官方 tp.json）
 */
export type BetterGIDomainCatalogItem = {
    /**
     * 秘境名称（与 BGI 传送点/每周秘境 DomainName 一致）
     */
    name: string;
    /**
     * 所在地区
     */
    region?: string;
    /**
     * 产出表类别/兜底时 tp.json 的 domain type
     */
    category?: string;
    /**
     * 三档奖励物品名（顺序即 BGI 领奖序号 1/2/3；圣遗物或无数据时为空数组）
     */
    rewards?: Array<string>;
};
