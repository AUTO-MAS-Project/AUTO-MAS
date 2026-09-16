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
     * DirectExe 模式下启动游戏前临时把 Unity 注册表分辨率固定为 1920×1080 窗口，关闭后恢复
     */
    ForceResolution1920x1080?: (boolean | null);
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
};

