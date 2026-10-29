/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
export type MaaEndInventoryOptions = {
    /**
     * 上游库存目标填写说明
     */
    description: string;
    /**
     * 上游库存目标输入字段
     */
    inputs: Array<ComboBoxItem>;
    /**
     * 上游库存任务领取方式
     */
    claimModes: Array<ComboBoxItem>;
};

