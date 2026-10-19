/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcConfig_Run = {
    /**
     * 游戏更新时间限制（分钟）
     */
    GameUpdateTimeLimit?: (number | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 版本落后时是否由 MAS 自动下载并安装安装包
     */
    IfAutoInstallGameApk?: (boolean | null);
    /**
     * 是否在登录游戏前检查游戏更新
     */
    IfCheckGameUpdate?: (boolean | null);
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行时间限制（分钟）
     */
    RunTimeLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 任务切换方式
     */
    TaskTransitionMethod?: ('ExitGame' | 'ExitEmulator' | null);
};

