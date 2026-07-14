/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-EF 游戏配置（仅保留首版运行需要字段）
 */
export type OkefConfig_Game = {
    /**
     * 游戏相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 兼容旧配置：ok-script 固定先启动游戏
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 游戏程序路径
     */
    Path?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏等待启动时间
     */
    WaitTime?: (number | null);
};

