/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PlanConfigData } from './PlanConfigData';
import type { PlanIndexItem } from './PlanIndexItem';
import type { UnavailableConfigItem } from './UnavailableConfigItem';
export type PlanGetOut = {
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
    uiSources?: Array<string>;
    /**
     * 计划索引列表
     */
    index: Array<PlanIndexItem>;
    /**
     * 计划列表或单个计划数据
     */
    data: Record<string, PlanConfigData>;
    /**
     * 所属插件不可用的计划表，只在获取全部计划时给出；只能删除
     */
    unavailable?: Array<UnavailableConfigItem>;
};

