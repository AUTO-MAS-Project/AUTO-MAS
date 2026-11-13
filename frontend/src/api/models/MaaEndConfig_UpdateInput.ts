/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_UpdateInput = {
    /**
     * 运行前由 MAS 下载、校验并安装 MaaEnd 官方完整包；不暂停 MXU 自身的更新检查
     */
    TakeoverEnabled?: (boolean | null);
    /**
     * 全量或优先增量；增量有风险，无可信缓存、匹配增量包或校验失败时回退全量
     */
    PackageMode?: ('full' | 'incremental' | null);
    /**
     * MaaEnd 更新通道
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * MaaEnd Mirror 酱 CDK，留空使用全局 CDK，无 CDK 使用 GitHub
     */
    MirrorChyanCDK?: (string | null);
};
