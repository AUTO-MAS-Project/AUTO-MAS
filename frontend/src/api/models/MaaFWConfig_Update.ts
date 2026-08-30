/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Update = {
    /**
     * 是否在运行前自动更新 MaaFW 项目
     */
    IfAutoUpdate?: (boolean | null);
    /**
     * 项目更新源，留空时使用全局更新源
     */
    Source?: ('' | 'MirrorChyan' | 'GitHub' | null);
    /**
     * 项目更新渠道，留空时使用全局更新渠道
     */
    Channel?: ('' | 'stable' | 'beta' | null);
    /**
     * Mirror 酱 CDK，留空时使用全局项目更新 CDK
     */
    MirrorChyanCDK?: (string | null);
    /**
     * GitHub 仓库覆盖
     */
    GitHubRepo?: (string | null);
    /**
     * GitHub release tag 覆盖
     */
    GitHubTag?: (string | null);
    /**
     * GitHub release asset 文件名匹配模式
     */
    GitHubAssetPattern?: (string | null);
};

