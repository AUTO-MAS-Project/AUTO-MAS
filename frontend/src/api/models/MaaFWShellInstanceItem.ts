/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWShellInstanceItem = {
    /**
     * 实例 ID（导入时原样传回）
     */
    id: string;
    /**
     * 外壳里的实例名
     */
    name: string;
    /**
     * 导入后的用户名（与已有用户、同名实例重名时带「 (2)」这类后缀）
     */
    userName: string;
    /**
     * 实例来自哪个外壳
     */
    source: MaaFWShellInstanceItem.source;
    /**
     * 是否是外壳上次使用的实例
     */
    active?: boolean;
    /**
     * 实例队列里勾选着的任务数
     */
    taskCount?: number;
    /**
     * 实例的控制方式（给人看的名字）
     */
    controller?: string;
    /**
     * 实例的资源（给人看的名字）
     */
    resource?: string;
};
export namespace MaaFWShellInstanceItem {
    /**
     * 实例来自哪个外壳
     */
    export enum source {
        MFAAVALONIA = 'MFAAvalonia',
        MXU = 'MXU',
        MFW_PY_QT6 = 'MFW-PyQt6',
    }
}

