/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
/**
 * 任务级配置字段（元数据 + 当前值）
 *
 * type 决定前端渲染方式：select 下拉 / bool 开关 / number 数字 /
 * plan_list 计划列表（columns 行内字段元数据 + newItem 新增行默认值）。
 */
export type ZzzOdAppConfigFieldOut = {
    /**
     * 配置字段名（app yml 中的键）
     */
    field: string;
    /**
     * 展示标题
     */
    title: string;
    /**
     * 字段类型：select/bool/number/team/plan_list
     */
    type?: string;
    /**
     * 当前值（plan_list 为计划列表）
     */
    value?: null;
    /**
     * 可选项列表
     */
    options?: Array<ComboBoxItem>;
    /**
     * plan_list 行内字段元数据（field/title/type/options/showWhen；showWhen 为条件 dict 或条件列表，条件含 not 取反）
     */
    columns?: null;
    /**
     * plan_list 新增行的默认值
     */
    newItem?: (Record<string, any> | null);
};

