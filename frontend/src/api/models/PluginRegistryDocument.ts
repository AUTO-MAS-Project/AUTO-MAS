/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginConfigUi } from './PluginConfigUi';
import type { PluginRecord_info } from './PluginRecord_info';
/**
 * 沿用配置字段投影，并显式保留命令目标身份及运行时 UI 属性。
 */
export type PluginRegistryDocument = {
    /**
     * 插件注册表项
     */
    info?: (PluginRecord_info | null);
    uid: string;
    ui: PluginConfigUi;
    disableImpact?: Array<'scripts' | 'games'>;
};

