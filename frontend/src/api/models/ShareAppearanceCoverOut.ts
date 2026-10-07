/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAppearanceCoverOut = {
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
     * 封面图片的 data URL
     */
    dataUrl?: string;
    /**
     * 封面所在的版本号, 取最新版本时为空
     */
    versionNo?: (number | null);
};

