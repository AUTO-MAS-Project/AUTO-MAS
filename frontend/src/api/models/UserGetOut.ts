/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Output } from './GeneralUserConfig_Output';
import type { MaaUserConfig_Output } from './MaaUserConfig_Output';
import type { UserIndexItem } from './UserIndexItem';
export type UserGetOut = {
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
     * 用户索引列表
     */
    index: Array<UserIndexItem>;
    /**
     * 用户数据字典, key来自于index列表的uid
     */
    data: Record<string, (MaaUserConfig_Output | GeneralUserConfig_Output)>;
};

