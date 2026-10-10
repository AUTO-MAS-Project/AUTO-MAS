/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAppearanceCoverIn = {
    /**
     * 分享站文件 ID
     */
    fileId: number;
    /**
     * 版本号, 为空表示最新版本; inheritable 为真时忽略
     */
    versionNo?: (number | null);
    /**
     * 为真时取发新版本不带封面时分享站会沿用的那张: 最近一个未被驳回且带封面的版本
     */
    inheritable?: boolean;
};

