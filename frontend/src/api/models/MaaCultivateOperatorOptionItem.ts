/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaCultivateGoalOptionItem } from './MaaCultivateGoalOptionItem';
export type MaaCultivateOperatorOptionItem = {
    /**
     * 干员 ID
     */
    value: string;
    /**
     * 干员名
     */
    label: string;
    /**
     * 稀有度
     */
    rarity?: number;
    /**
     * 职业
     */
    profession?: string;
    /**
     * 精英化可达档位上限（1/2/3★ 与上游缺数据者恒 0）
     */
    maxElite?: number;
    /**
     * 有精英化体系但需求数据缺失（区别于 1/2/3★ 结构上不设精英化）
     */
    dataMissing?: boolean;
    /**
     * 专精目标选项（value=skillId，label=技能名）
     */
    skills?: Array<MaaCultivateGoalOptionItem>;
    /**
     * 模组目标选项（value=uniEquipId，label=模组名（分支））
     */
    modules?: Array<MaaCultivateGoalOptionItem>;
};

