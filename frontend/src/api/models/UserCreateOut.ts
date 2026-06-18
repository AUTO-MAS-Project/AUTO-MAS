/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig } from './GeneralUserConfig';
import type { HSRUserConfig } from './HSRUserConfig';
import type { M9AUserConfig } from './M9AUserConfig';
import type { MaaEndUserConfig } from './MaaEndUserConfig';
import type { MaaUserConfig } from './MaaUserConfig';
import type { OkwwUserConfig } from './OkwwUserConfig';
import type { SrcUserConfig } from './SrcUserConfig';
export type UserCreateOut = {
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
     * 新创建的用户ID
     */
    userId: string;
    /**
     * 用户配置数据
     */
    data: (MaaUserConfig | SrcUserConfig | GeneralUserConfig | OkwwUserConfig | MaaEndUserConfig | M9AUserConfig | HSRUserConfig);
};

