/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 插件安装的跨进程结果；准备完成仍须等待新进程加载确认。
 */
export type PluginInstallation = {
    installationId: string;
    metaId: string;
    packageName: string;
    pluginName: string;
    version: string;
    state: PluginInstallation.state;
    message?: (string | null);
};
export namespace PluginInstallation {
    export enum state {
        WAITING_RESTART = 'waiting_restart',
        APPLYING = 'applying',
        SUCCEEDED = 'succeeded',
        FAILED = 'failed',
    }
}

