/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NoticeOut = {
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
     * 是否需要显示公告
     */
    if_need_show: boolean;
    /**
     * 公告信息, key为公告标题, value为公告内容
     */
    data: Record<string, string>;
};

