/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcConfig_UpdateInput = {
    /**
     * 运行前由 MAS 预取 SRC 原生代码源并调用官方安装器完成更新，普通下载失败后沿用当前安装；运行期暂停原生更新并在任务结束后恢复
     */
    TakeoverEnabled?: (boolean | null);
};

