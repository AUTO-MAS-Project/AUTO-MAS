/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskMode } from './TaskMode';
export type ComboBoxItem = {
    /**
     * 展示值
     */
    label: string;
    /**
     * 实际值
     */
    value: (string | null);
    /**
     * 任务项支持的执行模式；非脚本项为空
     */
    supported_modes?: (Array<TaskMode> | null);
};

