/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
import type { ZzzOdTrainCategoryOut } from './ZzzOdTrainCategoryOut';
/**
 * 任务计划的动态选项（静态读取安装目录，与一条龙原生 GUI 同源）
 */
export type ZzzOdTaskOptionsOut = {
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
     * 应用ID
     */
    appId: string;
    /**
     * 「训练」tab 副本级联树
     */
    trainCategories?: Array<ZzzOdTrainCategoryOut>;
    /**
     * 迷失之地图层列表
     */
    lostVoidMissions?: Array<string>;
    /**
     * 配队方案选项
     */
    autoBattle?: Array<ComboBoxItem>;
    /**
     * 迷失之地挑战配置选项
     */
    challenge?: Array<ComboBoxItem>;
};

