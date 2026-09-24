/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2SlotAssignment } from './Emulator2SlotAssignment';
export type Emulator2PathAddOut = {
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
     * 是否添加成功
     */
    ok?: boolean;
    /**
     * 失败原因枚举, 与搜索结果同一套
     */
    reason?: string;
    /**
     * 路径标识, 由安装目录派生
     */
    pathId?: string;
    /**
     * 安装别名
     */
    alias?: string;
    /**
     * 模拟器类型
     */
    type?: string;
    /**
     * 探测到的版本号
     */
    version?: string;
    /**
     * 本次新分配的设备号
     */
    assignedSlots?: Array<Emulator2SlotAssignment>;
    /**
     * 重新添加同一路径时沿用的原设备号
     */
    revivedSlots?: Array<string>;
};

