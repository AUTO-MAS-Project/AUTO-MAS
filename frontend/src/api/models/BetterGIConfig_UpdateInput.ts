/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIConfig_UpdateInput = {
    /**
     * 运行前由 MAS 下载校验 BetterGI 官方安装包并静默更新，普通检查下载失败后沿用当前安装；运行期暂时屏蔽本体更新提示，结束恢复
     */
    TakeoverEnabled?: (boolean | null);
    /**
     * BetterGI 正式版或公测版（上游 alpha）
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * BetterGI Mirror 酱 CDK，留空使用全局 CDK，无 CDK 使用 GitHub
     */
    MirrorChyanCDK?: (string | null);
};

