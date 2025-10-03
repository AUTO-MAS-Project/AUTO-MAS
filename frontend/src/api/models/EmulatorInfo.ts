/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 模拟器信息
 */
export type EmulatorInfo = {
    /**
     * 模拟器名称
     */
    name: string;
    /**
     * 模拟器类型
     */
    type: string;
    /**
     * 模拟器路径
     */
    path: string;
    /**
     * 最大等待时间
     */
    max_wait_time: number;
    /**
     * 老板键列表
     */
    boss_keys?: Array<string>;
};

