/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWResourceInfo = {
    /**
     * 资源名称
     */
    name: string;
    /**
     * 资源显示名称
     */
    label?: (string | null);
    /**
     * 资源描述
     */
    description?: (string | null);
    /**
     * 资源图标路径
     */
    icon?: (string | null);
    /**
     * 资源路径列表
     */
    path?: Array<string>;
    /**
     * 适用控制器列表
     */
    controller?: Array<string>;
    /**
     * 资源选项
     */
    option?: Array<string>;
};

