/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcUserConfig_Data } from './SrcUserConfig_Data';
import type { SrcUserConfig_Info } from './SrcUserConfig_Info';
import type { SrcUserConfig_Notify } from './SrcUserConfig_Notify';
import type { SrcUserConfig_Stage } from './SrcUserConfig_Stage';
export type SrcUserConfig = {
    /**
     * 基础信息
     */
    Info?: (SrcUserConfig_Info | null);
    /**
     * 关卡配置
     */
    Stage?: (SrcUserConfig_Stage | null);
    /**
     * 用户数据
     */
    Data?: (SrcUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (SrcUserConfig_Notify | null);
};

