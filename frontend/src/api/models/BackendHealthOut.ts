/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 后端核心服务与后台初始化状态。
 */
export type BackendHealthOut = {
    /**
     * 核心 API 是否可用
     */
    ready: boolean;
    /**
     * 后台初始化状态
     */
    backgroundStatus: string;
    /**
     * 后台初始化失败原因
     */
    backgroundError?: (string | null);
};

