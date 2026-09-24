/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUpdateData = {
    /**
     * 外部脚本引擎
     */
    engine: HSRUpdateData.engine;
    /**
     * 是否成功查到版本信息
     */
    checked?: boolean;
    /**
     * 本次是否真的完成了更新
     */
    updated?: boolean;
    /**
     * 当前已安装版本
     */
    current_version?: (string | null);
    /**
     * 可用的最新版本
     */
    latest_version?: (string | null);
    /**
     * 是否有新版本
     */
    update_available?: boolean;
    /**
     * 新版本能否从当前下载源安装（CDK 失效时为假）
     */
    installable?: boolean;
    /**
     * 面向用户的结果说明
     */
    message?: string;
};
export namespace HSRUpdateData {
    /**
     * 外部脚本引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}

