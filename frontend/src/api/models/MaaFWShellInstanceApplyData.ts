/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWShellInstanceImportItem } from './MaaFWShellInstanceImportItem';
/**
 * 覆盖到已有用户的结果：除了逐项成败与跳过项，还带实际写进用户配置的任务快照。
 *
 * 界面直接拿它刷新本地状态，不用再回头拉一次用户配置——那样会把用户还没保存的其它改动
 * 一起冲掉。快照与 ``info`` 都是写入漏斗处理之后的样子（特调整理、密码加密），与读用户配置
 * 拿到的一致。
 */
export type MaaFWShellInstanceApplyData = {
    /**
     * 这次覆盖的结果；失败原因在 result.error 里，连结果是空的（找不到用户 / 实例）时为 null
     */
    result?: (MaaFWShellInstanceImportItem | null);
    /**
     * 实际写进用户配置的任务快照；失败时为空
     */
    snapshot?: (Record<string, any> | null);
    /**
     * 写入时特调一并改掉的用户信息字段（如 M9A 把切换账号收进 Account）；没有为空
     */
    info?: Record<string, any>;
};

