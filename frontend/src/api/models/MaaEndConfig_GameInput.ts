/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_GameInput = {
    /**
     * 终末地游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 结束后是否关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 控制器类型
     */
    ControllerType?: (string | null);
    /**
     * 模拟器 ID
     */
    EmulatorId?: (string | null);
    /**
     * 模拟器索引
     */
    EmulatorIndex?: (string | null);
    /**
     * 是否在任务启动前检查并自动更新终末地 PC 客户端
     */
    IfAutoUpdate?: (boolean | null);
    /**
     * 鹰角官方启动器路径（Launcher.exe 或 Games.exe）
     */
    LauncherPath?: (string | null);
    /**
     * 终末地游戏路径
     */
    Path?: (string | null);
    /**
     * 关闭游戏时恢复的显示模式，与具体分辨率独立配置
     */
    RestoreDisplayType?: ('Window' | 'Fullscreen' | null);
    /**
     * 关闭游戏时恢复分辨率；Original 复用启动前读取的注册表值
     */
    RestoreResolution?: ('Off' | 'Original' | '1920x1080' | '2560x1440' | '3840x2160' | 'Custom' | null);
    /**
     * 自定义恢复分辨率高度
     */
    RestoreResolutionHeight?: (number | null);
    /**
     * 自定义恢复分辨率宽度
     */
    RestoreResolutionWidth?: (number | null);
    /**
     * 是否在启动游戏时执行 MaaEnd 分辨率设置预任务
     */
    SetResolution?: (boolean | null);
    /**
     * 游戏客户端更新时长限制（分钟）
     */
    UpdateTimeLimit?: (number | null);
    /**
     * 等待时间（秒）
     */
    WaitTime?: (number | null);
};

