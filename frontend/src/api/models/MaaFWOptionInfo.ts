/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWOptionCaseInfo } from './MaaFWOptionCaseInfo';
import type { MaaFWOptionHotkeyInfo } from './MaaFWOptionHotkeyInfo';
import type { MaaFWOptionInputInfo } from './MaaFWOptionInputInfo';
export type MaaFWOptionInfo = {
    /**
     * 选项名称
     */
    name: string;
    /**
     * 选项类型
     */
    type: string;
    /**
     * 选项显示名称
     */
    label?: (string | null);
    /**
     * 选项描述
     */
    description?: (string | null);
    /**
     * 选项图标路径
     */
    icon?: (string | null);
    /**
     * 适用控制器
     */
    controller?: Array<string>;
    /**
     * 适用资源
     */
    resource?: Array<string>;
    /**
     * 可选 case
     */
    cases?: Array<MaaFWOptionCaseInfo>;
    /**
     * 输入项
     */
    inputs?: Array<MaaFWOptionInputInfo>;
    /**
     * 热键项
     */
    hotkeys?: Array<MaaFWOptionHotkeyInfo>;
    /**
     * 默认 case
     */
    defaultCase?: (string | Array<string> | null);
};

