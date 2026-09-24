/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 碧蓝档案活动数据查询参数
 */
export type BlueArchiveActivityIn = {
    /**
     * 服务器：JP 日服 / Globle 国际服 / CN 国服（原文拼写如此）
     */
    line_type: BlueArchiveActivityIn.line_type;
    /**
     * 页码，从 1 开始
     */
    page?: number;
    /**
     * 每页条数
     */
    page_size?: number;
};
export namespace BlueArchiveActivityIn {
    /**
     * 服务器：JP 日服 / Globle 国际服 / CN 国服（原文拼写如此）
     */
    export enum line_type {
        JP = 'JP',
        GLOBLE = 'Globle',
        CN = 'CN',
    }
}

