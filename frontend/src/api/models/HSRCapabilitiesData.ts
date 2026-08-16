/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRCapabilityAdapter } from './HSRCapabilityAdapter';
import type { HSRCapabilityTask } from './HSRCapabilityTask';
export type HSRCapabilitiesData = {
    /**
     * 契约版本
     */
    revision?: string;
    /**
     * HSR 是否可用
     */
    available?: boolean;
    /**
     * 不可用原因
     */
    unavailable_reason?: (string | null);
    /**
     * 候代引擎
     */
    candidate_engines?: Array<'M7A' | 'SRA'>;
    /**
     * 已配置引擎
     */
    configured_engines?: Array<'M7A' | 'SRA'>;
    /**
     * 有效引擎
     */
    effective_engines?: Array<'M7A' | 'SRA'>;
    /**
     * 支持的运行模式
     */
    supported_modes?: Array<string>;
    /**
     * 引擎适配器
     */
    adapters?: Array<HSRCapabilityAdapter>;
    /**
     * 任务列表
     */
    tasks?: Array<HSRCapabilityTask>;
    /**
     * 兼容性警告
     */
    warnings?: Array<string>;
    /**
     * 浏览器能力
     */
    browser?: (Record<string, any> | null);
};

