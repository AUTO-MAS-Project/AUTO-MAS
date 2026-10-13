/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimeSetEntry_Input } from './TimeSetEntry_Input';
export type TimeSetUpdateIn = {
    /**
     * 所属队列 ID
     */
    queueId: string;
    /**
     * 定时项 ID
     */
    timeSetId: string;
    /**
     * 定时项补丁（文档形状）
     */
    data: TimeSetEntry_Input;
};

