/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaConfig_RunInput = {
    /**
     * 剿灭时间限制（分钟）
     */
    AnnihilationTimeLimit?: (number | null);
    /**
     * 游戏更新时间限制（分钟）
     */
    GameUpdateTimeLimit?: (number | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 是否允许自动下载并安装游戏安装包（仅官服）
     */
    IfAutoInstallGameApk?: (boolean | null);
    /**
     * 是否在启动 MAA 前检查游戏更新
     */
    IfCheckGameUpdate?: (boolean | null);
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 日常时间限制（分钟）
     */
    RoutineTimeLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 任务切换方式
     */
    TaskTransitionMethod?: ('NoAction' | 'ExitGame' | 'ExitEmulator' | null);
};

