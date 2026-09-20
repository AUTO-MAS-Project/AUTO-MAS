/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ZZZ-OD 启动器可用性（独立配置侧切换原始/集成启动器用）
 */
export type ZzzOdLauncherOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 原始启动器（OneDragon-Launcher.exe）是否已安装
     */
    original_available: boolean;
    /**
     * 集成启动器（OneDragon-RuntimeLauncher.exe）是否已安装
     */
    integrated_available: boolean;
};

