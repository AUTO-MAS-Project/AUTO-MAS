/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ShareAppearanceUploadItem } from './ShareAppearanceUploadItem';
export type ShareAppearanceUploadsOut = {
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
     * 当前登录账号的外观上传记录
     */
    data?: Array<ShareAppearanceUploadItem>;
};

