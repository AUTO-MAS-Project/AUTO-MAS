/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSConfig_Game = {
    /**
     * 游戏生命周期模式
     */
    LaunchMode?: ('DirectExe' | 'AttachOnly' | null);
    /**
     * DirectExe 模式下要启动的游戏 exe
     */
    LaunchPath?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 启动游戏后等待窗口就绪的时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * DirectExe 下临时改写 Unity 游戏分辨率的尺寸
     */
    UnityResolution?: ('Off' | '1920x1080' | '1280x720' | null);
};

