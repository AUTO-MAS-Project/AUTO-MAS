/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralConfig_Game = {
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
     * 自定义协议URL
     */
    URL?: (string | null);
    /**
     * 游戏进程名称
     */
    ProcessName?: (string | null);
};

