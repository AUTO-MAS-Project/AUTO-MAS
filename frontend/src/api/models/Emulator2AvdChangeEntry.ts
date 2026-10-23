/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdChangeGroup } from './Emulator2AvdChangeGroup';
export type Emulator2AvdChangeEntry = {
    /**
     * 版本号, 如 v34.0.0
     */
    version: string;
    /**
     * 构建号写法, 如 mas-34
     */
    label: string;
    /**
     * 按分类排好的摘要
     */
    groups?: Array<Emulator2AvdChangeGroup>;
};

