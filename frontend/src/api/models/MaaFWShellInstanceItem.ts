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
    /**
     * 实例里记着的键位：{hotkey 选项名: {字段名: 组合键}}，只含 interface 里声明过的hotkey 选项与字段、非空的值（全局 / 资源级在前，任务级覆盖），不与默认值比较；读不到 interface 时为空
     */
    hotkeys?: Record<string, Record<string, string>>;
    /**
     * 扫到这份配置的目录（同一次列表里都一样）
     */
    sourceDir?: string;
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

