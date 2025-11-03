/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ClickTextIn = {
    /**
     * 窗口标题（用于查找窗口）
     */
    window_title: string;
    /**
     * 要查找并点击的文字内容
     */
    text: string;
    /**
     * 截图间隔时间（秒）
     */
    interval?: number;
    /**
     * 重复截图次数
     */
    retry_times?: number;
};

