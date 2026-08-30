/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWTaskInfo = {
    /**
     * 任务名称
     */
    name: string;
    /**
     * 任务显示名称
     */
    label?: (string | null);
    /**
     * MaaFW pipeline 入口
     */
    entry: string;
    /**
     * 任务描述
     */
    description?: (string | null);
    /**
     * 任务图标路径
     */
    icon?: (string | null);
    /**
     * 所属分组
     */
    group?: Array<string>;
    /**
     * 适用控制器
     */
    controller?: Array<string>;
    /**
     * 适用资源
     */
    resource?: Array<string>;
    /**
     * 任务选项
     */
    option?: Array<string>;
    /**
     * 是否默认勾选
     */
    defaultCheck?: boolean;
};

