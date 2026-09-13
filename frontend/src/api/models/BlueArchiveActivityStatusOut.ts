/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 碧蓝档案活动状态：进行中的活动，或下一个未开始的活动
 */
export type BlueArchiveActivityStatusOut = {
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
     * 当前是否有进行中的活动
     */
    Running?: boolean;
    /**
     * 进行中的活动名称
     */
    Name?: string;
    /**
     * 进行中活动的开始时间
     */
    StartTime?: string;
    /**
     * 进行中活动的结束时间
     */
    EndTime?: string;
    /**
     * 下一个活动的名称
     */
    NextName?: string;
    /**
     * 下一个活动的开始时间
     */
    NextStartTime?: string;
};

