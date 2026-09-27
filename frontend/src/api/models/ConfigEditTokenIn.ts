/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ConfigEditTokenIn = {
    /**
     * 配置物理文件资源键
     */
    resourceKey: ConfigEditTokenIn.resourceKey;
    /**
     * 编辑租约令牌
     */
    editLeaseToken: string;
};
export namespace ConfigEditTokenIn {
    /**
     * 配置物理文件资源键
     */
    export enum resourceKey {
        CONFIG = 'Config',
        EMULATOR_CONFIG = 'EmulatorConfig',
        PLAN_CONFIG = 'PlanConfig',
        SCRIPT_CONFIG = 'ScriptConfig',
        QUEUE_CONFIG = 'QueueConfig',
        TOOLS_CONFIG = 'ToolsConfig',
    }
}

