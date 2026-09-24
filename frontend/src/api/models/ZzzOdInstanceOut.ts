/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * zzz-od 实例（账号）信息
 */
export type ZzzOdInstanceOut = {
    /**
     * 实例下标（config/{idx:02d} 目录）
     */
    idx: number;
    /**
     * 实例名称
     */
    name: string;
    /**
     * 是否为当前活跃实例
     */
    active: boolean;
    /**
     * 是否参与「全部实例」模式的一条龙
     */
    active_in_od: boolean;
    /**
     * 运行前切换账号（一条龙原生能力：运行到该实例前强制登录其账号）
     */
    force_login_before_run?: boolean;
};

