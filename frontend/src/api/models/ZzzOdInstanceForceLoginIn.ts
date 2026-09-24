/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直控：切换实例「运行前切换账号」（一条龙原生能力，MAS 不干涉）
 */
export type ZzzOdInstanceForceLoginIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标实例下标
     */
    instanceIdx: number;
    /**
     * 是否开启运行前切换账号
     */
    forceLogin: boolean;
};

