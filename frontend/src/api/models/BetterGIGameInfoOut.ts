/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 游戏客户端信息（用户页透传展示）
 */
export type BetterGIGameInfoOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 生效游戏路径（用户级优先，否则 BGI 全局配置）
     */
    installPath?: (string | null);
    /**
     * BetterGI 全局配置的游戏路径原值
     */
    globalPath?: (string | null);
    /**
     * 识别到的客户端渠道，无法识别为 null
     */
    channel?: ('官服' | 'B服' | '国际服' | null);
    /**
     * 生效路径来源
     */
    source?: ('用户' | '全局' | null);
};

