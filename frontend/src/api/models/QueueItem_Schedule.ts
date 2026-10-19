/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItem_Schedule = {
    /**
     * 固定时间模式的执行周期
     */
    Days?: (Array<'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'> | null);
    /**
     * 是否参与循环调度
     */
    Enabled?: (boolean | null);
    /**
     * 间隔模式的计时基准: start 为上次开始, finish 为上次结束
     */
    IntervalAnchor?: ('start' | 'finish' | null);
    /**
     * 间隔模式的间隔分钟数
     */
    IntervalMinutes?: (number | null);
    /**
     * 循环调度模式: fixed_time 为固定时间, interval 为间隔
     */
    Mode?: ('fixed_time' | 'interval' | null);
    /**
     * 下次运行时间, 空值哨兵表示由调度器按模式推算
     */
    NextRunAt?: (string | null);
    /**
     * 固定时间模式的执行时间
     */
    Time?: (string | null);
};

