/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndPlanConfig_Info = {
    /**
     * 计划表名称
     */
    Name?: string;
    /**
     * 计划表模式
     */
    Mode?: MaaEndPlanConfig_Info.Mode;
};
export namespace MaaEndPlanConfig_Info {
    /**
     * 计划表模式
     */
    export enum Mode {
        ALL = 'ALL',
        WEEKLY = 'Weekly',
    }
}

