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
    /**
     * 停用本插件及其级联下游时会删除的配置领域
     */
    disableImpact?: Array<'scripts' | 'games' | 'plans'>;
    /**
     * 直接上游插件名（requires 的提供者）
     */
    dependsOn?: Array<string>;
    /**
     * requires 中当前找不到提供者的服务名
     */
    missingServices?: Array<string>;
    /**
     * 停用或重载时会一并拆掉的下游插件名
     */
    disableCascade?: Array<string>;
    /**
     * 卸载时会一并卸掉的下游插件名
     */
    uninstallCascade?: Array<string>;
};

