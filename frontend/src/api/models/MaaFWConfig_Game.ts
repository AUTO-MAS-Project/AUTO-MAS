/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Game = {
    /**
     * 游戏启动模式：DirectExe 让 MAS 启动并在结束后关闭 / AttachOnly 使用其他方式启停，MAS 只接管
     */
    LaunchMode?: ('DirectExe' | 'AttachOnly' | null);
    /**
     * DirectExe 模式下 MAS 启动的游戏 exe
     */
    LaunchPath?: (string | null);
    /**
     * DirectExe 模式下启动 Unity 游戏前临时把注册表分辨率改成所选窗口尺寸，关闭后恢复；Off 不修改
     */
    UnityResolution?: ('Off' | '1920x1080' | '1280x720' | null);
    /**
     * 安卓游戏包名，留空则从项目的 pipeline 中自动识别
     */
    PackageName?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 游戏启动后等待窗口就绪的时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * 由 MAS 启动游戏时，窗口出现后至少再等多少秒才下发第一个任务（秒），0 关闭
     */
    StartupSettleTime?: (number | null);
};

