/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Update = {
    /**
     * 是否自动更新
     */
    IfAutoUpdate?: (boolean | null);
    /**
      * 更新源: GitHub源, Mirror酱源, 自建源, CNB源
     */
    Source?: ('GitHub' | 'MirrorChyan' | 'AutoSite' | 'CNB' | null);
    /**
     * 更新渠道: 稳定版, 测试版
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * 网络代理地址
     */
    ProxyAddress?: (string | null);
    /**
     * Mirror酱CDK
     */
    MirrorChyanCDK?: (string | null);
};

