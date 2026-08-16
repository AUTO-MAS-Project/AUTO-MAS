/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRCapabilityAdapter = {
    /**
     * 原生脚本引擎
     */
    engine: HSRCapabilityAdapter.engine;
    /**
     * 引擎展示名称
     */
    display_name: string;
    /**
     * 引擎版本
     */
    version?: (string | null);
    /**
     * 支持的运行模式
     */
    supported_modes?: Array<string>;
    /**
     * 引擎能力集合
     */
    capabilities?: Record<string, any>;
    /**
     * 引擎是否就绪
     */
    ready?: boolean;
    /**
     * 引擎状态说明
     */
    ready_reason?: (string | null);
};
export namespace HSRCapabilityAdapter {
    /**
     * 原生脚本引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}

