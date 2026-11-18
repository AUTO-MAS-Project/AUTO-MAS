/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginMetaInput } from './PluginMetaInput';
export type PluginCatalogUpdateIn = {
    /**
     * PluginMeta.uid
     */
    metaId: string;
    /**
     * 目录字段只读，仅允许提交安装触发器
     */
    data: PluginMetaInput;
};

