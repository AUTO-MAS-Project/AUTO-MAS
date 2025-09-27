/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Input } from './GeneralUserConfig_Input';
import type { MaaUserConfig_Input } from './MaaUserConfig_Input';
export type UserUpdateIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 用户ID
     */
    userId: string;
    /**
     * 用户更新数据
     */
    data: (MaaUserConfig_Input | GeneralUserConfig_Input);
};

