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
    /**
     * 后端自身支持的健康检查协议版本
     */
    protocol: number;
    /**
     * 后端版本号
     */
    version: string;
    /**
     * 后端所在提交哈希，未受监督或监督器未注入时为空
     */
    commit: string;
};

