/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorInfo } from './EmulatorInfo';
/**
 * 更新模拟器配置请求
 */
export type EmulatorUpdateIn = {
    /**
     * 模拟器ID
     */
    emulatorId: string;
    /**
     * 需要更新的模拟器配置数据
     */
    data: EmulatorInfo;
};

