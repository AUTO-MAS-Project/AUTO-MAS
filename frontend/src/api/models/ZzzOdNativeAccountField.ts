/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
/**
 * 直控编辑的账号字段（强绑定 zzz-od 原生 game_account.yml）。
 */
export type ZzzOdNativeAccountField = {
    /**
     * game_account.yml 字段名
     */
    key: string;
    /**
     * 展示标题
     */
    title: string;
    /**
     * 当前值（读自实例原生配置）
     */
    value?: (string | null);
    /**
     * 可选项列表（空=自由输入）
     */
    options?: Array<ComboBoxItem>;
};

