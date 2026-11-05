/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BAAHConfig_Update = {
    /**
     * 运行前由 MAS 下载校验并安装 BAAH 官方更新包，普通下载失败后沿用当前安装
     */
    TakeoverEnabled?: (boolean | null);
    /**
     * BAAH 更新通道
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * BAAH Mirror 酱 CDK，留空使用全局 CDK，无 CDK 使用 GitHub
     */
    MirrorChyanCDK?: (string | null);
};

