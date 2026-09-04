/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI AutoPathing 目录树节点
 */
export type BetterGIPathingNode = {
    /**
     * 目录名
     */
    name: string;
    /**
     * 子目录
     */
    dirs?: Array<BetterGIPathingNode>;
    /**
     * 该目录下路径文件名(不含 .json)
     */
    files?: Array<string>;
};

