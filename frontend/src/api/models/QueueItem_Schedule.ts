/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItem_Schedule = {
    /**
     * 是否启用循环调度
     */
    Enabled?: (boolean | null);
    /**
     * 循环调度模式
     */
    Mode?: ('fixed_time' | 'interval' | null);
    /**
     * 固定时间调度执行周期
     */
    Days?: (Array<'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'> | null);
    /**
     * 固定时间调度执行时间，格式 HH:mm
     */
    Time?: (string | null);
    /**
     * 间隔调度分钟数
     */
    IntervalMinutes?: (number | null);
    /**
     * 间隔调度基准
     */
    IntervalAnchor?: ('start' | 'finish' | null);
    /**
     * 下一次运行时间，格式 YYYY-MM-DD HH:mm:ss
     */
    NextRunAt?: (string | null);
};

