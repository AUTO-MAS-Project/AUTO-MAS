/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginConfigUi } from './PluginConfigUi';
import type { PluginMeta_info } from './PluginMeta_info';
/**
 * 市场条目的配置投影，包含安装操作的显隐和可编辑属性。
 */
export type PluginCatalogDocument = {
    /**
     * 目录项
     */
    info?: (PluginMeta_info | null);
    uid: string;
    ui: PluginConfigUi;
};

