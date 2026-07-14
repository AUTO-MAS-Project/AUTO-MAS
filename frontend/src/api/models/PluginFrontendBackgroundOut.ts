/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PluginFrontendBackgroundOut = {
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
     * 是否启用前端背景
     */
    enabled?: boolean;
    /**
     * 背景图片代理地址
     */
    image_url?: (string | null);
    /**
     * 模糊半径
     */
    blur_px?: number;
    /**
     * 亮度百分比
     */
    brightness?: number;
    /**
     * 图片透明度百分比
     */
    opacity?: number;
    /**
     * 遮罩透明度百分比
     */
    overlay_opacity?: number;
    /**
     * 卡片透明度百分比
     */
    card_opacity?: number;
    /**
     * 面板透明度百分比
     */
    panel_opacity?: number;
    /**
     * 浮层透明度百分比
     */
    elevated_opacity?: number;
    /**
     * 侧边栏透明度百分比
     */
    sider_opacity?: number;
    /**
     * 背景位置
     */
    position?: string;
    /**
     * 背景填充方式
     */
    fit?: string;
};

