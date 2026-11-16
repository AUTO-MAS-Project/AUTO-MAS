/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskParamValue_Output } from './TaskParamValue_Output';
export type TaskUserItem_info = {
    /**
     * 原用户 UUID，default 表示共享配置
     */
    user_id?: (string | null);
    name?: (string | null);
    status?: (string | null);
    params?: (Record<string, TaskParamValue_Output> | null);
    readonly result?: (string | null);
};

