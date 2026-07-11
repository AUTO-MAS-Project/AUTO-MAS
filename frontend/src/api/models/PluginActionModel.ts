/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PluginActionModel = {
    /**
     * 动作 ID
     */
    id: string;
    /**
     * 按钮标题
     */
    label: string;
    /**
     * 调用路径
     */
    path: string;
    /**
     * HTTP 方法
     */
    method?: string;
    /**
     * 默认请求载荷
     */
    payload?: any;
    /**
     * 插件名
     */
    plugin: string;
};

