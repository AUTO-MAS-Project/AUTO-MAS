/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 通用脚本用户记录。
 */
export type ScriptUserRecord = {
    /**
     * 用户 ID
     */
    id: string;
    /**
     * 所属脚本 ID
     */
    script_id: string;
    /**
     * 脚本类型键
     */
    type: string;
    /**
     * 用户名称
     */
    name: string;
    /**
     * 用户配置内容
     */
    config: Record<string, any>;
    /**
     * 用户配置表单描述
     */
    schema: Record<string, any>;
};

