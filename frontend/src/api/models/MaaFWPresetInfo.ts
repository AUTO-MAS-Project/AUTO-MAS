/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWTaskSnapshot } from './MaaFWTaskSnapshot';
export type MaaFWPresetInfo = {
    /**
     * 预设名称
     */
    name: string;
    /**
     * 预设显示名称
     */
    label?: (string | null);
    /**
     * 预设描述
     */
    description?: (string | null);
    /**
     * 预设声明任务数
     */
    taskCount?: number;
    /**
     * 转换后勾选任务数
     */
    checkedCount?: number;
    /**
     * 预设转换后的任务快照
     */
    snapshot: MaaFWTaskSnapshot;
};

