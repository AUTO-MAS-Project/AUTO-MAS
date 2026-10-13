/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Updates = {
    /**
     * 是否自动更新
     */
    if_auto_update?: boolean;
    /**
     * 更新源: GitHub源, Mirror酱源, 自建源, CNB 镜像源
     */
    source?: Updates.source;
    /**
     * 更新渠道: 稳定版, 测试版
     */
    channel?: Updates.channel;
    /**
     * 网络代理地址
     */
    proxy_address?: string;
    /**
     * Mirror酱CDK
     */
    mirror_chyan_cdk?: string;
    /**
     * GitHub token/API key
     */
    github_token?: string;
    /**
     * 暂停自动更新检查的截止日期 YYYY-MM-DD，空字符串表示未暂停
     */
    pause_until?: string;
};
export namespace Updates {
    /**
     * 更新源: GitHub源, Mirror酱源, 自建源, CNB 镜像源
     */
    export enum source {
        GIT_HUB = 'GitHub',
        MIRROR_CHYAN = 'MirrorChyan',
        AUTO_SITE = 'AutoSite',
        CNB = 'CNB',
    }
    /**
     * 更新渠道: 稳定版, 测试版
     */
    export enum channel {
        STABLE = 'stable',
        BETA = 'beta',
    }
}

