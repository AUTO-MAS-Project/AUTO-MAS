/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OCRScreenshotIn = {
    /**
     * 窗口标题（用于查找窗口）
     */
    window_title: string;
    /**
     * 是否预处理图片区域，True时排除边框和标题栏，False时使用完整窗口
     */
    should_preprocess?: boolean;
    /**
     * 宽高比宽度
     */
    aspect_ratio_width?: number;
    /**
     * 宽高比高度
     */
    aspect_ratio_height?: number;
    /**
     * 自定义截图区域 (left, top, width, height)
     */
    region?: (any[] | null);
};

