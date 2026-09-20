/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2SearchItem } from './Emulator2SearchItem';
export type Emulator2SearchOut = {
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
     * 搜索结果, 不可添加的也会列出并说明原因
     */
    emulators?: Array<Emulator2SearchItem>;
};

