/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRSRAProfile } from './HSRSRAProfile';
export type HSRSRAProfilesData = {
    /**
     * 原生脚本引擎
     */
    engine?: string;
    /**
     * 档案目录（%APPDATA%/SRA/configs）
     */
    root: string;
    /**
     * 档案目录是否可读且至少有一份档案
     */
    available?: boolean;
    /**
     * 不可用原因
     */
    unavailable_reason?: (string | null);
    /**
     * 脚本配置的档案 id；空串表示自动
     */
    configured?: string;
    /**
     * 自动模式会选中的档案 id
     */
    auto_id: string;
    /**
     * 当前实际生效的档案 id
     */
    selected: string;
    /**
     * 配置的档案不存在、已回退到自动选择
     */
    fallback?: boolean;
    /**
     * 回退说明
     */
    fallback_reason?: (string | null);
    /**
     * 可选档案
     */
    profiles?: Array<HSRSRAProfile>;
};

