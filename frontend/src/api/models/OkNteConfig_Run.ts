/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteConfig_Run = {
    /**
     * 已弃用：宿主不再读取，仅在升级时迁入桌面分身清单
     */
    ExecutionSession?: ('main' | 'desktop' | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 日志超时限制
     */
    RunTimeLimit?: (number | null);
    /**
     * 重试次数限制
     */
    RunTimesLimit?: (number | null);
};

