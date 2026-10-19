/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralConfig_Game = {
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 模拟器 ID
     */
    EmulatorId?: (string | null);
    /**
     * 模拟器索引
     */
    EmulatorIndex?: (string | null);
    /**
     * 是否启用游戏
     */
    Enabled?: (boolean | null);
    /**
     * 是否强制关闭
     */
    IfForceClose?: (boolean | null);
    /**
     * 游戏路径
     */
    Path?: (string | null);
    /**
     * 游戏进程名称
     */
    ProcessName?: (string | null);
    /**
     * 游戏类型
     */
    Type?: ('Emulator' | 'Client' | 'URL' | null);
    /**
     * 自定义协议URL
     */
    URL?: (string | null);
    /**
     * 等待时间（秒）
     */
    WaitTime?: (number | null);
};

