/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 某 JsScript 脚本目录 settings.json 的 UI 定义（双击项目设置弹窗渲染用）
 */
export type BetterGIScriptSettingsUiOut = {
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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * settings.json UI 定义数组（name/type/label/options/default）
     */
    data?: Array<Record<string, any>>;
};

