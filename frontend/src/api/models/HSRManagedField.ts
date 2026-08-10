/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRManagedField = {
    /**
     * 字段键
     */
    key: string;
    /**
     * 字段名称
     */
    label?: string;
    /**
     * 字段类型
     */
    type?: string;
    /**
     * 字段当前值
     */
    value?: any;
    /**
     * 字段说明
     */
    description?: (string | null);
    /**
     * 字段选项
     */
    options?: Array<any>;
    /**
     * 最小值
     */
    minimum?: (number | null);
    /**
     * 最大值
     */
    maximum?: (number | null);
    /**
     * 是否只读
     */
    readonly?: boolean;
};

