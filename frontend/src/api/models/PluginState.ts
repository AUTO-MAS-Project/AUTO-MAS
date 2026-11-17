/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 插件状态：稳态含未加载 / 干净禁用启用 / 两档故障；另五过渡。
 */
export enum PluginState {
    UNLOADED = 'unloaded',
    DISABLED = 'disabled',
    ENABLED = 'enabled',
    FAULT_LOAD = 'fault_load',
    FAULT_RUNTIME = 'fault_runtime',
    LOADING = 'loading',
    ENABLING = 'enabling',
    RELOADING = 'reloading',
    DISABLING = 'disabling',
    UNLOADING = 'unloading',
}
