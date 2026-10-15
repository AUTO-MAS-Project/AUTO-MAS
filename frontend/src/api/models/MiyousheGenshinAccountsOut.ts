/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MiyousheGenshinAccountOut } from './MiyousheGenshinAccountOut';
export type MiyousheGenshinAccountsOut = {
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
     * 社区账号组名称与凭据配置状态
     */
    data?: Array<MiyousheGenshinAccountOut>;
    /**
     * 脱敏失败原因标识
     */
    reason?: string;
};

