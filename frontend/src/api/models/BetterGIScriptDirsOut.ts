/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 常用目录与可执行文件绝对路径
 */
export type BetterGIScriptDirsOut = {
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
     * 脚本仓库检出目录
     */
    repoDir?: (string | null);
    /**
     * JS 脚本目录
     */
    jsScriptDir?: (string | null);
    /**
     * 地图追踪任务目录
     */
    autoPathingDir?: (string | null);
    /**
     * 一条龙配置目录
     */
    oneDragonDir?: (string | null);
    /**
     * 配置组目录
     */
    scriptGroupDir?: (string | null);
    /**
     * BetterGI 主程序路径
     */
    exePath?: (string | null);
};

