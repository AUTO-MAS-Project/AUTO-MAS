/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 奇想盒运行配置（复用通用三限语义 + 提权开关）
 */
export type WhimboxConfig_Run = {
    /**
     * 每日代理次数上限（0=不限）
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 重试次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 运行时间限制（分钟，日志静默超时判定）
     */
    RunTimeLimit?: (number | null);
    /**
     * 以管理员权限启动奇想盒后端（上游强制管理员，默认开启）
     */
    UseAdmin?: (boolean | null);
};

