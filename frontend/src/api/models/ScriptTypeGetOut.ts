/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ScriptTypeDescriptor } from './ScriptTypeDescriptor';
export type ScriptTypeGetOut = {
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
     * 脚本类型列表
     */
    data: Array<ScriptTypeDescriptor>;
};

