/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdTeamItemOut } from './ZzzOdTeamItemOut';
/**
 * 保存后的编队列表
 */
export type ZzzOdTeamsSaveOut = {
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
     * 编队列表
     */
    teams: Array<ZzzOdTeamItemOut>;
};

