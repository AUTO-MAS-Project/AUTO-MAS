/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIPathingNode } from './BetterGIPathingNode';
/**
 * BetterGI 地图追踪目录树（{RootPath}/User/AutoPathing 的递归结构）
 */
export type BetterGIPathingTreeOut = {
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
     * AutoPathing 绝对目录
     */
    root?: (string | null);
    /**
     * 顶层目录树
     */
    dirs?: Array<BetterGIPathingNode>;
};

