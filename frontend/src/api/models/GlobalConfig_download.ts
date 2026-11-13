/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_download = {
    /**
     * 统一下载并发上限
     */
    max_running?: (number | null);
    /**
     * 下载缓存容量上限（MB），超限时仅回收零引用文件
     */
    cache_mb?: (number | null);
    /**
     * 网络失败最大尝试次数
     */
    attempts?: (number | null);
    /**
     * 下载重试退避初始秒数
     */
    retry_delay?: (number | null);
};

