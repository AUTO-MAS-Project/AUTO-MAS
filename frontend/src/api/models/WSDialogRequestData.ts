/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 应用内弹窗请求数据 (id=Main, type=dialog.request)
 */
export type WSDialogRequestData = {
    /**
     * 弹窗请求ID, 响应使用相同ID关联
     */
    requestId: string;
    /**
     * 关联的任务ID
     */
    taskId?: (string | null);
    /**
     * 弹窗标题
     */
    title: string;
    /**
     * 弹窗正文
     */
    message: string;
    /**
     * 选项文案
     */
    options?: Array<string>;
};

