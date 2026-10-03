/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWShellInstanceImportItem } from './MaaFWShellInstanceImportItem';
/**
 * 覆盖到已有用户的结果：除了逐项成败与跳过项，还带一份算好的任务快照。
 *
 * 快照是换算出来的最终队列，界面直接拿去刷新本地状态，不用再回头拉一次用户配置——
 * 那样会把用户还没保存的其它改动一起冲掉。
 */
export type MaaFWShellInstanceApplyData = {
    /**
     * 这次覆盖的结果；失败原因在 result.error 里，连结果是空的（找不到用户 / 实例）时为 null
     */
    result?: (MaaFWShellInstanceImportItem | null);
    /**
     * 覆盖进用户的任务快照；失败时为空
     */
    snapshot?: (Record<string, any> | null);
};

