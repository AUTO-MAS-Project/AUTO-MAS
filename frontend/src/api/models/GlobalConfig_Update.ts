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
     * 更新源: GitHub源, Mirror酱源, 自建源, CNB 镜像源
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
     * MFW 项目包从 GitHub Release 下载时的加速镜像: Auto 依次试镜像并在全部失败后回退直连, Off 只直连
     */
    GitHubMirror?: ('Auto' | 'Off' | null);
    /**
     * Mirror酱CDK
     */
    MirrorChyanCDK?: (string | null);
};

