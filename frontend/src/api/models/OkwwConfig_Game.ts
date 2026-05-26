/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 游戏配置（鸣潮 PC 客户端）
 */
export type OkwwConfig_Game = {
    /**
     * 游戏管理相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 任务开始前是否由 MAS 启动游戏
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 任务结束后是否关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 类型: PC 客户端
     */
    Type?: ('Client' | null);
    /**
     * 游戏客户端路径
     */
    Path?: (string | null);
    /**
     * 自定义协议 URL
     */
    URL?: (string | null);
    /**
     * 游戏进程名称
     */
    ProcessName?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏启动等待时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * 是否强制关闭游戏进程
     */
    IfForceClose?: (boolean | null);
};
