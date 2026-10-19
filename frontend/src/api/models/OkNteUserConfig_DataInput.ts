/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteUserConfig_DataInput = {
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 上次代理状态（未知/成功/失败）
     */
    LastProxyStatus?: ('未知' | '成功' | '失败' | '维护中' | null);
    /**
     * 上次运行的 ok-nte 任务序号（-t N）
     */
    LastTaskIndex?: (number | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
};

