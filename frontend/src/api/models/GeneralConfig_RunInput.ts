/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralConfig_RunInput = {
    /**
     * 单独启动托管时使用的 Windows 会话
     */
    ExecutionSession?: ('main' | 'desktop' | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
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
};

