/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkScriptTaskItem } from './OkScriptTaskItem';
export type OkScriptProjectInfo = {
    /**
     * 项目名（安装包应用名，如 ok-ef）
     */
    appName: string;
    /**
     * 项目版本
     */
    version: string;
    /**
     * 是否为已验证可用的项目
     */
    verified: boolean;
    /**
     * 一次性任务列表
     */
    tasks: Array<OkScriptTaskItem>;
};

