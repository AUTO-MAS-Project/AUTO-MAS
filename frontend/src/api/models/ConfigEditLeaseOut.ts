/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ConfigEditLeaseOut = {
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
     * 配置物理文件资源键
     */
    resourceKey: string;
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 当前配置文件集合指纹
     */
    version: string;
    /**
     * 租约过期时间戳
     */
    expiresAt: number;
    /**
     * 资源当前是否被编辑锁占用
     */
    locked?: boolean;
};

