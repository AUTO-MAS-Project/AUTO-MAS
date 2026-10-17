/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameCalendarActivityInfo } from './GameCalendarActivityInfo';
export type GameCalendarActivitiesOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 用户已完成且未过期的活动
     */
    data?: Array<GameCalendarActivityInfo>;
};

