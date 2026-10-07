/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 配置加载过程中的一次自动规范化记录
 */
export type ConfigLoadEventOut = {
    /**
     * 配置项位置（形如 分组.字段名）
     */
    field: string;
    /**
     * 规范化前的原值
     */
    oldValue: string;
    /**
     * 规范化后的新值
     */
    newValue: string;
    /**
     * 自动纠正原因（如非法枚举被回退、密文不可解）
     */
    reason: string;
    /**
     * 该次规范化发生的时间
     */
    time: string;
};
