/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 独立于脚本日志的临时预下载展示状态。
 */
export type WSTaskPrefetchData = {
    /**
     * 下一托管名称
     */
    target?: string;
    /**
     * 检查、下载或准备状态
     */
    status?: string;
    /**
     * 当前包名
     */
    package?: string;
    /**
     * 实际下载方式 httpx 或 FluxDown
     */
    method?: string;
    /**
     * 当前文件进度，总大小未知时为空
     */
    progress?: string;
    /**
     * 已下载量与总大小
     */
    size?: string;
    /**
     * 当前下载速率
     */
    rate?: string;
};

