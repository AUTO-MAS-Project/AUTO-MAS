/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 游戏配置（复用通用字段）
 */
export type OkwwConfig_Game = {
    /**
     * 游戏/模拟器相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 类型: 模拟器, PC端, URL协议
     */
    Type?: ('Emulator' | 'Client' | 'URL' | null);
    /**
     * 游戏/模拟器程序路径
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
     * 游戏/模拟器启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏/模拟器等待启动时间
     */
    WaitTime?: (number | null);
    /**
     * 是否强制关闭游戏/模拟器进程
     */
    IfForceClose?: (boolean | null);
    /**
     * 模拟器ID
     */
    EmulatorId?: (string | null);
    /**
     * 模拟器多开实例索引
     */
    EmulatorIndex?: (string | null);
    /**
     * 任务开始前是否由 MAS 启动游戏/模拟器
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 任务结束后是否关闭游戏/模拟器
     */
    CloseOnFinish?: (boolean | null);
};
