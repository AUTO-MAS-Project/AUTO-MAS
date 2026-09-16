/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直控编辑的一条龙游戏启动参数（强绑定 zzz-od 原生 game.yml）。
 */
export type ZzzOdNativeLaunchArgs = {
    /**
     * 启动参数总开关（关闭时一条龙启动游戏不带任何参数）
     */
    launch_argument: boolean;
    /**
     * 窗口尺寸（1920x1080/2560x1440/3840x2160）
     */
    screen_size: string;
    /**
     * 全屏模式：0=窗口化 1=全屏
     */
    full_screen: string;
    /**
     * 无边框窗口（-popupwindow）
     */
    popup_window: boolean;
    /**
     * DX12 启动（写回时把 -use-d3d12 合并进高级参数）
     */
    dx12: boolean;
    /**
     * 显示器序号（1-4）
     */
    monitor: string;
    /**
     * 高级参数（原样透传给一条龙拼接，上游不解析）
     */
    launch_argument_advance: string;
};

