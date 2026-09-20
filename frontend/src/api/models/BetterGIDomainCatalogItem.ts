/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 每周秘境可选秘境目录项（来源：官方 tp.json，唯一数据源）
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
     * tp.json 的 domain type（BlessDomain/ForgeryDomain/MasteryDomain）
     */
    category?: string;
    /**
     * 三档奖励物品名（顺序即 BGI 领奖序号 1/2/3；圣遗物秘境为套装两件）
     */
    rewards?: Array<string>;
};

