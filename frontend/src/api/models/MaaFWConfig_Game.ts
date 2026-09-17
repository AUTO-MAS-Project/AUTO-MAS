/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Game = {
    /**
     * 游戏启动模式
     */
    LaunchMode?: ('AttachOnly' | 'DirectExe' | null);
    /**
     * DirectExe 模式下 MAS 启动的游戏 exe
     */
    LaunchPath?: (string | null);
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
    /**
     * 任务结束后是否关闭由 MAS 启动的游戏
     */
    CloseOnFinish?: (boolean | null);
};

