/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameCalendarActivityUpdateIn = {
    /**
     * 活动名称
     */
    name: string;
    /**
     * 活动开始时间，包含时区
     */
    startTime: string;
    /**
     * 活动结束时间，包含时区
     */
    endTime: string;
    /**
     * 是否由用户标记为已完成
     */
    completed: boolean;
};

