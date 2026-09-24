/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 单个目标干员的当前练度（编辑器"当前等级 → 目标等级"展示用）。
 */
export type CultivateOperatorProgression = {
    /**
     * 干员 ID
     */
    operatorId: string;
    /**
     * 练度来源（skland/local/manual）；default 表示无实测数据
     */
    source: string;
    /**
     * 当前精英化阶段 0-2
     */
    elite: number;
    /**
     * 当前干员等级
     */
    level: number;
    /**
     * 当前专精等级（skillId → 0-3）
     */
    masteries?: Record<string, number>;
    /**
     * 当前模组等级（uniEquipId → 0-3）
     */
    modules?: Record<string, number>;
};

