/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginMeta } from './PluginMeta';
export type PluginCatalogUpdateIn = {
    /**
     * PluginMeta.uid
     */
    metaId: string;
    /**
     * 补丁；透传全部字段，不做白名单过滤
     */
    data: PluginMeta;
};

