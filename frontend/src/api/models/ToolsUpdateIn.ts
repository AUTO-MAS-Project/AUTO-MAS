/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ToolsConfig } from './ToolsConfig';
export type ToolsUpdateIn = {
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 工具配置需要更新的数据
     */
    data: ToolsConfig;
};

