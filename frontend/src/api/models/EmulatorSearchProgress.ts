/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EmulatorSearchProgress = {
    /**
     * 是否正在扫描
     */
    active?: boolean;
    /**
     * 扫描阶段
     */
    phase?: string;
    /**
     * 总盘符数量
     */
    total_drives?: number;
    /**
     * 已完成盘符数量
     */
    completed_drives?: number;
    /**
     * 当前扫描盘符
     */
    current_drive?: string;
    /**
     * 当前扫描目录路径
     */
    current_path?: string;
    /**
     * 已发现模拟器数量
     */
    found_count?: number;
    /**
     * 扫描耗时（秒）
     */
    elapsed_seconds?: number;
    /**
     * 扫描进度百分比
     */
    progress_percent?: number;
};

