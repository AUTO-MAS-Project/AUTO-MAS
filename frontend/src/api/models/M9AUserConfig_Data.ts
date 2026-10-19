/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AUserConfig_Data = {
    /**
     * 是否通过检查
     */
    IfPassCheck?: (boolean | null);
    /**
     * 上次代理日期
     */
    LastProxyDate?: (string | null);
    /**
     * 上次运行状态
     */
    LastProxyStatus?: (string | null);
    /**
     * MaaFW 周期任务完成记录，结构为 weekly/monthly -> task name -> period key
     */
    PeriodTaskRecords?: (string | null);
    /**
     * 代理次数
     */
    ProxyTimes?: (number | null);
};

