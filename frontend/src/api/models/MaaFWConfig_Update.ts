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
};

