/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 开发模式下读取或保存 MAA 内置预设的结果。
 */
export type MaaBasePresetOut = {
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
     * MAA 预设内容
     */
    data?: Record<string, any>;
    /**
     * 预设文件路径
     */
    path?: string;
};

