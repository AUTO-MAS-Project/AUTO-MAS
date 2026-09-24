/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWShellConfigTask } from './MaaFWShellConfigTask';
export type MaaFWShellConfigImportData = {
    /**
     * 按外壳顺序排好的任务队列
     */
    tasks?: Array<MaaFWShellConfigTask>;
    /**
     * 项目里没有、或取值不认识而跳过的项
     */
    skipped?: Array<string>;
};

