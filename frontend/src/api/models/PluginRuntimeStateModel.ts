/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PluginRuntimeStateModel = {
    /**
     * 实例ID
     */
    instance_id: string;
    /**
     * 插件名
     */
    plugin: string;
    /**
     * 运行状态
     */
    status?: string;
    /**
     * 记录创建时间
     */
    created_at?: (string | null);
    /**
     * 发现时间
     */
    discovered_at?: (string | null);
    /**
     * 代码加载时间
     */
    loaded_at?: (string | null);
    /**
     * 激活时间
     */
    activated_at?: (string | null);
    /**
     * 销毁时间
     */
    disposed_at?: (string | null);
    /**
     * 卸载时间
     */
    unloaded_at?: (string | null);
    /**
     * 最近错误
     */
    last_error?: (string | null);
    /**
     * 最近错误时间
     */
    last_error_at?: (string | null);
};

