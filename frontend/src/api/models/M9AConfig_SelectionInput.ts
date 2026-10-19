/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AConfig_SelectionInput = {
    /**
     * 当前阶段保留：manager.py 仍从 Selection.* 读取运行范围， 字段迁移到 Info.* / 用户任务配置属于后续 P3 前端回收。 选中的 controller 列表
     */
    Controller?: (string | null);
    /**
     * 选中的 resource 列表
     */
    Resource?: (string | null);
    /**
     * 选中的 task 列表
     */
    Tasks?: (string | null);
};

