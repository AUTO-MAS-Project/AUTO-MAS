/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaPlanConfig_Info } from './MaaPlanConfig_Info';
import type { MaaPlanConfig_Item } from './MaaPlanConfig_Item';
export type MaaPlanConfig = {
    /**
     * 基础信息
     */
    Info?: (MaaPlanConfig_Info | null);
    /**
     * 全局
     */
    ALL?: (MaaPlanConfig_Item | null);
    /**
     * 每天的槽位：周计划用 Monday~Sunday 做键，多天轮换用 "1"~"N" 做键
     */
    Days?: Record<string, MaaPlanConfig_Item>;
};

