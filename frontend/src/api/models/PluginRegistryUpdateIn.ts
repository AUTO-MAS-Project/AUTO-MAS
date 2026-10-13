/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginRecord } from './PluginRecord';
export type PluginRegistryUpdateIn = {
    /**
     * PluginRecord.uid
     */
    recordId: string;
    /**
     * 补丁；服务端剔除非 Trigger
     */
    data: PluginRecord;
};

