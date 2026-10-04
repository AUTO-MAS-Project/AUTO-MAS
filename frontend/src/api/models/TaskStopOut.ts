/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskStopOut = {
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
     * MAA 配置回写结果；未确认或其他专项时为空
     */
    configResult?: 'saved' | 'config_read_failed' | 'config_not_written' | 'queue_changed' | 'failed' | 'closed' | null;
};
