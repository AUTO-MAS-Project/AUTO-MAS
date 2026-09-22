/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_Game = {
    /**
     * 控制器类型
     */
    ControllerType?: (string | null);
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
     * 是否在启动游戏时设置分辨率
     */
    SetResolution?: (boolean | null);
    /**
     * 启动游戏时的显示模式
     */
    GameSettingDisplayType?: ('Window' | 'Fullscreen' | null);
    /**
     * 启动游戏时的分辨率，Original 表示读取注册表
     */
    GameSettingResolution?: ('Original' | '1280x720' | '1920x1080' | '2560x1440' | null);
    /**
     * 结束后关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 关闭游戏时恢复的显示模式
     */
    RestoreDisplayType?: ('Window' | 'Fullscreen' | null);
    /**
     * 关闭游戏时恢复的分辨率，Off 表示不修改
     */
    RestoreResolution?: ('Off' | 'Original' | '1920x1080' | '2560x1440' | '3840x2160' | 'Fullscreen' | 'Custom' | null);
    /**
     * 自定义恢复分辨率宽度
     */
    RestoreResolutionWidth?: (number | null);
    /**
     * 自定义恢复分辨率高度
     */
    RestoreResolutionHeight?: (number | null);
};

