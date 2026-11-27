/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OptionValue } from './OptionValue';
export type TriggerWriteIn = {
    configUid: string;
    group: string;
    field: string;
    value: (boolean | null);
    /**
     * 下拉动作启动时传给处理器的选项值
     */
    option?: (OptionValue | null);
};

