/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UpdateCheckOut = {
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
     * 是否需要更新前端
     */
    if_need_update: boolean;
    /**
     * 最新前端版本号
     */
    latest_version: string;
    /**
     * 版本更新信息：版本号 -> 分类 -> 条目，只含比当前版本新的版本段，按版本号降序
     */
    update_info: Record<string, Record<string, Array<string>>>;
};

