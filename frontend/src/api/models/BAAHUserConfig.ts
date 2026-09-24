/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHUserConfig_Data } from './BAAHUserConfig_Data';
import type { BAAHUserConfig_Info } from './BAAHUserConfig_Info';
import type { BAAHUserConfig_Notify } from './BAAHUserConfig_Notify';
export type BAAHUserConfig = {
    /**
     * 用户信息
     */
    Info?: (BAAHUserConfig_Info | null);
    /**
     * 用户数据
     */
    Data?: (BAAHUserConfig_Data | null);
    /**
     * 单独通知
     */
    Notify?: (BAAHUserConfig_Notify | null);
};

