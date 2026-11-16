/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * FluxDown 下载历史中的一条记录。
 */
export type FluxdownRecord = {
    /**
     * 下载地址
     */
    url?: (string | null);
    /**
     * 落盘路径
     */
    destination?: (string | null);
    /**
     * 文件字节数
     */
    size?: (number | null);
    /**
     * 下载耗时（毫秒）
     */
    duration_ms?: (number | null);
    /**
     * 分段数
     */
    segments?: (number | null);
    /**
     * 使用的代理
     */
    proxy?: (string | null);
    /**
     * 校验信息
     */
    checksum?: (string | null);
    /**
     * 状态：success、failed、checksum_fail、fluxdown_fallback
     */
    status?: (string | null);
    /**
     * 失败原因
     */
    error?: (string | null);
    /**
     * 发生时间
     */
    timestamp?: (string | null);
};

