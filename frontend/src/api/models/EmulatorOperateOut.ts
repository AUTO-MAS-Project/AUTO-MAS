/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 模拟器操作响应：校验同步、执行异步。
 *
 * 校验通过时返回 ``code=200, status="accepted", operationId, accepted=True``，
 * 真实结果通过 WS ``emulator.notice`` 携带 ``operationId`` 推送。
 * 校验失败返回 ``code=400, status="error"``。
 */
export type EmulatorOperateOut = {
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
     * 操作追踪 ID；操作已接受但未完成时返回
     */
    operationId?: (string | null);
    /**
     * 操作是否已被接受进行后台执行
     */
    accepted?: boolean;
};

