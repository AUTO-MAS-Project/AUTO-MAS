/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItem_Schedule = {
    /**
     * 是否参与循环调度
     */
    Enabled?: (boolean | null);
    /**
     * 循环调度模式, 固定时间或间隔
     */
    Mode?: ('fixed_time' | 'interval' | null);
    /**
     * 固定时间模式的执行周期, 可多选
     */
    Days?: (Array<'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'> | null);
    /**
     * 固定时间模式的执行时间, 格式为HH:MM
     */
    Time?: (string | null);
    /**
     * 间隔模式的间隔分钟数
     */
    IntervalMinutes?: (number | null);
    /**
     * 间隔模式的计时基准, 上次开始或上次结束
     */
    IntervalAnchor?: ('start' | 'finish' | null);
    /**
     * 下次运行时间, 格式为YYYY-MM-DD HH:MM:SS
     */
    NextRunAt?: (string | null);
};
