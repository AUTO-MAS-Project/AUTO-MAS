/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * MaaFW 选择项的 API DTO。
 *
 * ConfigBase 将这三个列表以 JSON 字符串保存；API 同时接受已解析的
 * 字符串列表，便于后续编辑页直接提交结构化值。
 */
export type MaaFWConfig_Selection = {
    /**
     * 选中的 controller 名称 JSON 字符串或列表
     */
    Controller?: (string | Array<string> | null);
    /**
     * 选中的 resource 名称 JSON 字符串或列表
     */
    Resource?: (string | Array<string> | null);
    /**
     * 选中的 task 名称 JSON 字符串或列表
     */
    Tasks?: (string | Array<string> | null);
};

