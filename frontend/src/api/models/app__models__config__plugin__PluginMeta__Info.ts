/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Virtual_list_str__ } from './Virtual_list_str__';
import type { Virtual_str_ } from './Virtual_str_';
export type app__models__config__plugin__PluginMeta__Info = {
    /**
     * 包名
     */
    package_name?: string;
    /**
     * 插件名
     */
    plugin_name?: string;
    /**
     * 版本
     */
    version?: string;
    /**
     * 文档 URL
     */
    docs_url?: string;
    /**
     * 主页 URL
     */
    homepage?: string;
    /**
     * Requires-Dist 列表
     */
    requires_dist?: Array<string>;
    /**
     * 展示名 i18n 字典
     */
    display_name_i18n?: Record<string, string>;
    /**
     * 描述 i18n 字典
     */
    description_i18n?: Record<string, string>;
    /**
     * 标签 i18n 字典
     */
    tags_i18n?: Record<string, Array<string>>;
    display_name?: Virtual_str_;
    description?: Virtual_str_;
    tags?: Virtual_list_str__;
    /**
     * 安装（写 True 开闸）
     */
    install?: boolean;
};

