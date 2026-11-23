/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwConfig_RunInput = {
    /**
     * 单独启动托管时使用的 Windows 会话
     */
    ExecutionSession?: ('main' | 'desktop' | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 每日代理次数上限
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 单次运行超时时间
     */
    RunTimeLimit?: (number | null);
    /**
     * 单次任务重试次数
     */
    RunTimesLimit?: (number | null);
};

