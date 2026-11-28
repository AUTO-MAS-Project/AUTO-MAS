/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BackgroundTaskState } from './BackgroundTaskState';
export type TriggerTaskResult = {
    state: BackgroundTaskState;
    errorCode?: (string | null);
    /**
     * 失败原因，仅可展示的异常（如插件错误）填写
     */
    message?: (string | null);
    /**
     * 失败原因的结构化附加信息
     */
    detail?: (Record<string, any> | null);
};

