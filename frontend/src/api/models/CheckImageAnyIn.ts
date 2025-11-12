/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CheckImageAnyIn = {
    /**
     * 窗口标题（用于查找窗口）
     */
    window_title: string;
    /**
     * 要查找的图片路径列表
     */
    image_paths: Array<string>;
    /**
     * 截图间隔时间（秒）
     */
    interval?: number;
    /**
     * 重复截图次数
     */
    retry_times?: number;
    /**
     * 图像匹配阈值，范围 0-1
     */
    threshold?: number;
};

