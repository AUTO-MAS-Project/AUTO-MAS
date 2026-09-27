/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 游戏社区账号组删除请求
 */
export type GameSignAccountDeleteIn = {
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 账号组 UUID
     */
    accountId: string;
};

