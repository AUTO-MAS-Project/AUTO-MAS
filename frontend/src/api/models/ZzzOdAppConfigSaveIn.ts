/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 保存任务级配置（字段白名单校验后写入绑定槽；直控可指定原生实例）
 */
export type ZzzOdAppConfigSaveIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标用户ID
     */
    userId: string;
    /**
     * 应用ID
     */
    appId: string;
    /**
     * 字段名 → 值（plan_list 为计划列表）
     */
    values: Record<string, any>;
    /**
     * 直控模式：直接写入的原生实例下标（缺省写入用户绑定槽）
     */
    instanceIdx?: (number | null);
};

