/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Schedule = {
    /**
     * 参与循环调度
     */
    enabled?: boolean;
    /**
     * 循环排期方式
     */
    mode?: Schedule.mode;
    days?: Array<string>;
    /**
     * 固定执行时间
     */
    time?: string;
    interval_minutes?: number;
    interval_anchor?: Schedule.interval_anchor;
    /**
     * 下次运行时间，由主计时器维护
     */
    next_run_at?: (string | null);
};
export namespace Schedule {
    /**
     * 循环排期方式
     */
    export enum mode {
        FIXED_TIME = 'fixed_time',
        INTERVAL = 'interval',
    }
    export enum interval_anchor {
        START = 'start',
        FINISH = 'finish',
    }
}

