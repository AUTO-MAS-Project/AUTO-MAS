/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CultivatePreviewItem = {
    /**
     * 物品ID
     */
    itemId: string;
    /**
     * 物品名称
     */
    name: string;
    /**
     * 需求数量（保有量目标）
     */
    count: number;
    /**
     * 推荐关卡；刷取计划条目有值，材料需求/不可获取类为空
     */
    stage?: (string | null);
    /**
     * 刷取该条目到保有量目标的期望理智；固定产出关不可估算，为空
     */
    expectedSanity?: (number | null);
};

