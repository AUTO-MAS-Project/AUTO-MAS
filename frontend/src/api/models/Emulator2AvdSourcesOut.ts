/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdSourceItem } from './Emulator2AvdSourceItem';
export type Emulator2AvdSourcesOut = {
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
     * 按速度从快到慢排序, 失败的在最后
     */
    sources?: Array<Emulator2AvdSourceItem>;
    /**
     * 推荐的下载源标识 (最快的)
     */
    recommended?: string;
};

