/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HookMetaItem = {
    /**
     * Hook 文件路径
     */
    path: string;
    /**
     * Hook 名称
     */
    name?: (string | null);
    /**
     * Hook 描述
     */
    description?: (string | null);
    /**
     * 元数据读取状态
     */
    status?: HookMetaItem.status;
    /**
     * 警告/错误信息
     */
    warning?: (string | null);
};
export namespace HookMetaItem {
    /**
     * 元数据读取状态
     */
    export enum status {
        OK = 'ok',
        WARNING = 'warning',
    }
}

