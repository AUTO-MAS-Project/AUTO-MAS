/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSUserConfig_Data = {
    /**
     * 上次代理状态
     */
    LastProxyStatus?: ('未知' | '成功' | '失败' | '维护中' | '运行中' | null);
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
    /**
     * MaaFW 周期任务完成记录，结构为 weekly/monthly -> task name -> period key
     */
    PeriodTaskRecords?: (string | null);
};

