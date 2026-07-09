/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 游戏配置（复用通用字段）
 */
export type OkwwConfig_Game = {
    /**
     * 游戏相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 任务开始前是否由 MAS 启动游戏
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

