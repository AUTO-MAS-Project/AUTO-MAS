/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MiyousheGenshinRoleOut } from './MiyousheGenshinRoleOut';
export type MiyousheGenshinRolesOut = {
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
     * 账号绑定的原神官服角色
     */
    data?: Array<MiyousheGenshinRoleOut>;
    /**
     * 脱敏失败原因标识
     */
    reason?: string;
};

