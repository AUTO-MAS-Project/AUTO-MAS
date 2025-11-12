/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OCRScreenshotOut = {
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
     * 截图的Base64编码（PNG格式）
     */
    image_base64: string;
    /**
     * 实际使用的截图区域 (left, top, width, height)
     */
    region: any[];
    /**
     * 截图宽度
     */
    image_width: number;
    /**
     * 截图高度
     */
    image_height: number;
};

