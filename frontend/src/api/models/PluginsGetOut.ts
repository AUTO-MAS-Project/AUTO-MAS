/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginInstanceModel } from './PluginInstanceModel';
import type { PluginRuntimeStateModel } from './PluginRuntimeStateModel';
export type PluginsGetOut = {
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
     * 配置版本
     */
    version?: number;
    /**
     * 已发现插件
     */
    discovered_plugins?: Array<string>;
    /**
     * 插件Schema映射
     */
    schemas?: Record<string, Record<string, any>>;
    /**
     * 插件Schema加载错误
     */
    schema_errors?: Record<string, string>;
    /**
     * 插件实例列表
     */
    instances?: Array<PluginInstanceModel>;
    /**
     * 插件实例运行态
     */
    runtime_states?: Record<string, PluginRuntimeStateModel>;
    /**
     * 前端页面声明
     */
    pages?: Array<{
        id: string;
        path: string;
        title: string;
        menu_label: string;
        icon?: string;
        component: string;
        renderer?: string;
        url?: string | null;
        frontend_plugin?: string | null;
        element_tag?: string | null;
        entry_asset_url?: string | null;
        style_asset_urls?: Array<string>;
        manifest_version?: number | null;
        section?: string;
        order?: number;
        visible?: boolean;
        dev_only?: boolean;
        source?: string;
    }>;
    /**
     * 页面声明警告
     */
    page_errors?: Array<string>;
};
