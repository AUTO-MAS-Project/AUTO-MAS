/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ProjectInterface 预设转换出的任务快照，三个字段的键都是任务 name。
 *
 * 与用户自己的任务快照同构。用户队列允许同一个任务加多份，那边的键是任务
 * 实例 id（首份就是任务 name）；预设里的重复任务会被折叠，因此这里只有 name。
 */
export type MaaFWTaskSnapshot = {
    /**
     * 任务 name 顺序
     */
    taskOrder?: Array<string>;
    /**
     * 任务勾选状态
     */
    taskChecked?: Record<string, boolean>;
    /**
     * 任务选项值
     */
    taskOptions?: Record<string, Record<string, (string | Array<string> | Record<string, string>)>>;
};

