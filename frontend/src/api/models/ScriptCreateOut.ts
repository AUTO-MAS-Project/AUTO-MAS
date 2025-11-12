/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig } from './GeneralConfig';
import type { MaaConfig } from './MaaConfig';
export type ScriptCreateOut = {
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
     * 新创建的脚本ID
     */
    scriptId: string;
    /**
     * 脚本配置数据
     */
    data: (MaaConfig | GeneralConfig);
};

