/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2InstanceCreateOut = {
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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 是否新建成功
     */
    ok?: boolean;
    /**
     * 失败原因枚举
     */
    reason?: string;
    /**
     * 新实例分到的设备号
     */
    slot?: string;
    /**
     * 模拟器自己的实例索引
     */
    nativeIndex?: string;
};

