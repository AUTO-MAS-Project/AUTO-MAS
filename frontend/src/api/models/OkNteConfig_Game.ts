/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-NTE 游戏配置
 */
export type OkNteConfig_Game = {
    /**
     * 游戏相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 类型: PC端, URL协议
     */
    Type?: ('Client' | 'URL' | null);
    /**
     * 游戏程序路径
     */
    Path?: (string | null);
    /**
     * 自定义协议URL
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
     * 游戏等待启动时间
     */
    WaitTime?: (number | null);
    /**
     * 是否强制关闭游戏进程
     */
    IfForceClose?: (boolean | null);
    /**
     * 任务开始前是否由 MAS 启动游戏
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 任务结束后是否关闭游戏
     */
    CloseOnFinish?: (boolean | null);
};

