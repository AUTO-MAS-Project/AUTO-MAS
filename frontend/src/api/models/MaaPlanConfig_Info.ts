/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaPlanConfig_Info = {
    /**
     * 计划表名称
     */
    Name?: (string | null);
    /**
     * 计划表模式
     */
    Mode?: ('ALL' | 'Weekly' | 'Rotate' | null);
    /**
     * 多天轮换的天数，仅 Rotate 模式使用
     */
    RotateDays?: (number | null);
};

