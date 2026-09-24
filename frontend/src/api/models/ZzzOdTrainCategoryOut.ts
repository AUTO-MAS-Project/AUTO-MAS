/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdMissionTypeOut } from './ZzzOdMissionTypeOut';
/**
 * 「训练」tab 副本分类（体力刷本/恶名狩猎级联选项）
 */
export type ZzzOdTrainCategoryOut = {
    /**
     * 分类名（配置取值）
     */
    name: string;
    /**
     * 分类展示名
     */
    label: string;
    /**
     * 类型列表
     */
    mission_types?: Array<ZzzOdMissionTypeOut>;
};

