/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameTaskStatusOut = {
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
     * 是否有任务运行中
     */
    running?: boolean;
    /**
     * 当前阶段
     */
    phase?: string;
    /**
     * 进度百分比
     */
    percent?: number;
    /**
     * 已下载字节
     */
    downloaded?: number;
    /**
     * 总字节
     */
    total?: number;
    /**
     * 速度 B/s
     */
    speed?: number;
    /**
     * 详细信息
     */
    detail?: string;
};

