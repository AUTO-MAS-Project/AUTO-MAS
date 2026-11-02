/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaConfig_UpdateInput = {
    /**
     * 更新接管一次性迁移版本
     */
    TakeoverMigrationVersion?: (number | null);
    /**
     * 本脚本的 Mirror 酱 CDK（加密存储，留空回退 MAS 全局配置）
     */
    MirrorChyanCDK?: (string | null);
    /**
     * 是否接管 MAA 本体与资源更新（关=完全由 MAA 自行处理）
     */
    TakeoverEnabled?: (boolean | null);
    /**
     * MAA 更新通道：正式版或公测版
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * 更新通道一次性迁移版本
     */
    ChannelMigrationVersion?: (number | null);
};

