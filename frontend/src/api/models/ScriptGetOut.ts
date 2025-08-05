/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptGetOut = {
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
     * 脚本索引列表
     */
    index: Array<Record<string, string>>;
    /**
     * 脚本列表或单个脚本数据
     */
    data: Record<string, any>;
};

