/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShareTemplateItem } from './ShareTemplateItem';
export type ShareTemplateListOut = {
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
     * 配置模板列表
     */
    items?: Array<ShareTemplateItem>;
    /**
     * 当前页码
     */
    page?: number;
    /**
     * 每页条数
     */
    pageSize?: number;
    /**
     * 模板总数
     */
    total?: number;
    /**
     * 是否还有下一页
     */
    hasNext?: boolean;
};

