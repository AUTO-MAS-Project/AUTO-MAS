/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWDesktopWindowInfo } from './MaaFWDesktopWindowInfo';
export type MaaFWWindowPreviewData = {
    /**
     * MaaFW 项目根目录
     */
    path: string;
    /**
     * 请求指定的 controller 名称
     */
    controllerName?: (string | null);
    /**
     * 匹配到的桌面窗口
     */
    windows?: Array<MaaFWDesktopWindowInfo>;
};

