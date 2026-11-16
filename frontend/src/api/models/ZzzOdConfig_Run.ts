/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdConfig_Run = {
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 每日代理次数上限
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 单次运行超时时间（分钟）；这是日志停滞超时（latest_time 距今），不是 总时长上限——一条龙持续写日志就不会触发；启动器层故障（不写应用层 日志）也靠它兜底超时后切换启动器
     */
    RunTimeLimit?: (number | null);
    /**
     * 单次任务重试次数
     */
    RunTimesLimit?: (number | null);
};

