/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_Game = {
    /**
     * 控制器类型
     */
    ControllerType?: ('Win32-Window' | 'Win32-Window-Background' | 'Win32-Front' | 'ADB' | null);
    /**
     * 终末地客户端路径
     */
    Path?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏等待时间
     */
    WaitTime?: (number | null);
    /**
     * 模拟器ID
     */
    EmulatorId?: (string | null);
    /**
     * 模拟器索引
     */
    EmulatorIndex?: (string | null);
    /**
     * 结束后关闭游戏
     */
    CloseOnFinish?: (boolean | null);
};

