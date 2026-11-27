/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 所属插件不可用、原样保留着的托管或计划表（不在 index / data 里）。
 */
export type UnavailableConfigItem = {
    /**
     * 唯一标识符
     */
    uid: string;
    /**
     * 盘上记录的配置类型名
     */
    type: string;
    /**
     * 类型显示名，不认识的类型即类型名
     */
    typeLabel: string;
    /**
     * 名称，取不到时为空
     */
    name?: string;
    /**
     * 所属插件名，不认识时为空
     */
    plugin?: (string | null);
    /**
     * plugin_unavailable：所属插件没装上或没启用；load_failed：插件在但解析不了
     */
    reason: UnavailableConfigItem.reason;
    /**
     * load_failed 时的错误摘要
     */
    detail?: string;
};
export namespace UnavailableConfigItem {
    /**
     * plugin_unavailable：所属插件没装上或没启用；load_failed：插件在但解析不了
     */
    export enum reason {
        PLUGIN_UNAVAILABLE = 'plugin_unavailable',
        LOAD_FAILED = 'load_failed',
    }
}

