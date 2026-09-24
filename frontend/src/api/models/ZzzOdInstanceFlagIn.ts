/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 直控：切换实例是否参与「全部实例」运行模式（active_in_od）
 */
export type ZzzOdInstanceFlagIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标实例下标
     */
    instanceIdx: number;
    /**
     * 是否参与「全部实例」模式
     */
    activeInOd: boolean;
};

