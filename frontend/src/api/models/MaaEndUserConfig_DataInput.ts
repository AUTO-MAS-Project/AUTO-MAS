/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndUserConfig_DataInput = {
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 上次代理状态
     */
    LastProxyStatus?: ('未知' | '成功' | '失败' | null);
    /**
     * MaaEnd 每日任务完成记录，结构为 daily -> task name -> 日期
     */
    PeriodTaskRecords?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
};

