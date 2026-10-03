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
     * 游戏启动等待时间（秒）：等窗口出现与等画面稳定各最多这么久，画面稳定即提前
     */
    WaitTime?: (number | null);
    /**
     * 脚本级键位，JSON 字符串 {option 名: {字段名: 组合键}}（如 "Ctrl+E"），只存与 interface 默认不同的字段；仅 Win32 控制器生效
     */
    Hotkeys?: (string | null);
};

