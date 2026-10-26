/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndConfig_RunInput = {
    /**
     * 账号切换方式（默认使用 MAAEND，MAS 为兼容入口）
     */
    AccountSwitchMethod?: ('MAS' | 'MAAEND' | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 任务失败时是否按 MaaEnd 的导出规则打包运行日志
     */
    IfSaveLogBundle?: (boolean | null);
    /**
     * 任务失败时保存日志包的目录，留空表示不保存
     */
    LogBundlePath?: (string | null);
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行超时阈值
     */
    RunTimeLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 任务切换方式
     */
    TaskTransitionMethod?: ('NoAction' | 'ExitGame' | null);
};

