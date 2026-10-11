/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSPlanConfig_Info = {
    /**
     * 计划表名称
     */
    Name?: string;
    /**
     * 计划表模式
     */
    Mode?: MSSPlanConfig_Info.Mode;
    /**
     * 多天轮换的天数，仅 Rotate 模式使用
     */
    RotateDays?: number;
};
export namespace MSSPlanConfig_Info {
    /**
     * 计划表模式
     */
    export enum Mode {
        ALL = 'ALL',
        WEEKLY = 'Weekly',
        ROTATE = 'Rotate',
    }
}

