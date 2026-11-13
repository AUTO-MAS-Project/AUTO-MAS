/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskPrefetchData } from './WSTaskPrefetchData';
export type TaskItem_current = {
    index?: (string | null);
    readonly log?: (string | null);
    /**
     * 整轮脚本安装恢复与下载失败结算摘要
     */
    recovery_summary?: (string | null);
    /**
     * 下一托管预下载状态
     */
    prefetch?: (WSTaskPrefetchData | null);
};

