/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Update = {
    /**
     * 外部脚本自动更新时机：Off 不更新 / AfterRun 全部用户跑完后
     */
    AutoUpdateMode?: ('Off' | 'AfterRun' | null);
    /**
     * 外部脚本更新渠道：稳定版 / 测试版，两个引擎共用
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * 三月七助手更新包下载源：GitHub / Mirror 酱（需自行填写 CDK）
     */
    M7ASource?: ('GitHub' | 'MirrorChyan' | null);
    /**
     * SRA 更新包下载源：AUTO-MAS 下载站（免 CDK，默认）/ GitHub / Mirror 酱（需自行填写 CDK）
     */
    SRASource?: ('AutoSite' | 'GitHub' | 'MirrorChyan' | null);
    /**
     * Mirror 酱 CDK，选择 Mirror 酱作为下载源时必填
     */
    MirrorChyanCDK?: (string | null);
};

