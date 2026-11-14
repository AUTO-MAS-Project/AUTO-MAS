/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UniversalPlanConfig_Info = {
    /**
     * 计划表名称
     */
    Name?: (string | null);
    /**
     * 计划表模式
     */
    Mode?: ('ALL' | 'Weekly' | 'Rotate' | null);
    /**
     * 多天轮换天数
     */
    RotateDays?: (number | null);
    /**
     * 本地换日小时
     */
    ResetHour?: (number | null);
    /**
     * 本地换日分钟
     */
    ResetMinute?: (number | null);
    /**
     * 所属脚本
     */
    readonly ScriptId?: (string | null);
};

