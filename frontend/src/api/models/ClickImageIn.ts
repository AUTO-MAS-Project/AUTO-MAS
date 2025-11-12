/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ClickImageIn = {
    /**
     * 窗口标题（用于查找窗口）
     */
    window_title: string;
    /**
     * 要查找并点击的图片路径
     */
    image_path: string;
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

