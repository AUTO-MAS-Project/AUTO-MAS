/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Update = {
    /**
     * 项目自动更新时机：Off 不更新 / BeforeRun 运行前 / AfterRun 全部用户跑完后
     */
    AutoUpdateMode?: ('Off' | 'BeforeRun' | 'AfterRun' | null);
    /**
     * [已废弃] 旧布尔开关，加载时迁移为 AutoUpdateMode，运行流程不再读取
     */
    IfAutoUpdate?: (boolean | null);
    /**
     * [已废弃] 项目更新源；版本检查固定走 Mirror 酱，下载源按 CDK 自动分流
     */
    Source?: ('' | 'MirrorChyan' | 'GitHub' | null);
    /**
     * 项目更新渠道：稳定版 / 测试版 / 内测版，留空时使用全局更新渠道
     */
    Channel?: ('' | 'stable' | 'beta' | 'alpha' | null);
    /**
     * Mirror 酱 CDK，留空时使用全局项目更新 CDK
     */
    MirrorChyanCDK?: (string | null);
    /**
     * [已废弃] GitHub 仓库覆盖，改为从 interface.json 推导
     */
    GitHubRepo?: (string | null);
    /**
     * [已废弃] GitHub release tag 覆盖
     */
    GitHubTag?: (string | null);
    /**
     * [已废弃] GitHub release asset 文件名匹配模式
     */
    GitHubAssetPattern?: (string | null);
};

