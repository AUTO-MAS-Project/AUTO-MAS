/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 任务目录条目：一条龙目标/参数字段（上游三件套机械转换）
 */
export type WhimboxOptionCatalogItem = {
    /**
     * 上游配置键
     */
    key: string;
    /**
     * 显示名（上游模板 description）
     */
    display: string;
    /**
     * 上游配置节
     */
    section: string;
    /**
     * 控件类型：bool/int/select/multi_select/text
     */
    field_type: string;
    /**
     * 值域候选
     */
    options?: Array<string>;
    /**
     * 上游模板默认值（布尔语义已归一为 bool）
     */
    default?: (boolean | number | string | Array<string> | null);
};

