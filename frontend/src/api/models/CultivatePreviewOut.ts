/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CultivatePreviewItem } from './CultivatePreviewItem';
export type CultivatePreviewOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 刷取计划（按推荐关执行的材料条目）
     */
    stages: Array<CultivatePreviewItem>;
    /**
     * 全量材料需求（已含合成折算）
     */
    demands: Array<CultivatePreviewItem>;
    /**
     * 不可获取材料（需游戏内另行获取）
     */
    unobtainable: Array<CultivatePreviewItem>;
    /**
     * 可估算刷取条目的期望理智合计（不含固定产出关）；无可估算条目时为空
     */
    totalExpectedSanity?: (number | null);
    /**
     * 是否存在干员识别档案
     */
    hasProgression: boolean;
    /**
     * 是否存在仓库识别档案
     */
    hasInventory: boolean;
};

