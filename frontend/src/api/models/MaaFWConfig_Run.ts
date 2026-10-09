/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Run = {
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 运行时间限制（分钟）
     */
    RunTimeLimit?: (number | null);
    /**
     * 单任务时限（分钟），0 表示不限
     */
    TaskTimeLimit?: (number | null);
    /**
     * 按任务名覆盖的单任务时限（分钟），值 0 表示不限
     */
    TaskTimeLimitOverrides?: (string | Record<string, any> | null);
    /**
     * 原地打转检测（实验性，默认关）
     */
    LoopGuard?: (boolean | null);
    /**
     * 每日正常完成一次后当天跳过的 MaaFW 任务名列表
     */
    DailyOnceTasks?: (string | Array<string> | null);
    /**
     * 每周正常完成一次后本周跳过的 MaaFW 任务名列表
     */
    WeeklyOnceTasks?: (string | Array<string> | null);
    /**
     * 每月正常完成一次后本月跳过的 MaaFW 任务名列表
     */
    MonthlyOnceTasks?: (string | Array<string> | null);
    /**
     * 游戏客户端更新：Off 不检查 / Check 落后时提示手动更新 / AutoInstall 落后时自动下载安装；仅支持的特调类型生效
     */
    GameUpdateMode?: ('Off' | 'Check' | 'AutoInstall' | null);
};

