/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_ManagedRemote = {
    /**
     * 托管资源远程来源
     */
    Source?: ('MirrorChyan' | 'GitHub' | null);
    /**
     * 托管资源更新渠道
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * MirrorChyan 资源 ID
     */
    MirrorChyanRID?: (string | null);
    /**
     * MirrorChyan CDK
     */
    MirrorChyanCDK?: (string | null);
    /**
     * GitHub 仓库
     */
    GitHubRepo?: (string | null);
    /**
     * GitHub release tag
     */
    GitHubTag?: (string | null);
    /**
     * GitHub asset 匹配模式
     */
    GitHubAssetPattern?: (string | null);
};

