/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginActionModel } from './PluginActionModel';
import type { PluginInstanceModel } from './PluginInstanceModel';
import type { PluginPackageModel } from './PluginPackageModel';
import type { PluginRouteModel } from './PluginRouteModel';
import type { PluginRuntimeStateModel } from './PluginRuntimeStateModel';
import type { PluginServiceModel } from './PluginServiceModel';
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
     * 插件服务声明
     */
    plugin_services?: Record<string, PluginServiceModel>;
    /**
     * 插件声明式服务路由
     */
    plugin_routes?: Record<string, Array<PluginRouteModel>>;
    /**
     * 插件声明式前端动作
     */
    plugin_actions?: Record<string, Array<PluginActionModel>>;
    /**
     * 插件实例列表
     */
    instances?: Array<PluginInstanceModel>;
    /**
     * 插件安装包信息
     */
    plugin_packages?: Record<string, PluginPackageModel>;
    /**
     * 插件实例运行态
     */
    runtime_states?: Record<string, PluginRuntimeStateModel>;
    /**
     * 前端页面声明
     */
    pages?: Array<Record<string, any>>;
    /**
     * 页面声明警告
     */
    page_errors?: Array<string>;
};

