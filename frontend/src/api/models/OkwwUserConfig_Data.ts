/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * OK-WW 用户数据（复用通用字段）
 */
export type OkwwUserConfig_Data = {
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
    /**
     * 上次代理状态（未知/成功/失败）
     */
    LastProxyStatus?: (string | null);
    /**
     * 上次运行的 ok-ww 任务序号（-t N）
     */
    LastTaskIndex?: (number | null);
};

