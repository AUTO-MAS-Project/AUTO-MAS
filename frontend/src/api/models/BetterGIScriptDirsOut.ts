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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
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
     * 键鼠脚本（录制）目录
     */
    keyMouseScriptDir?: (string | null);
    /**
     * 自动战斗策略目录（User/AutoFight，*.txt / *.json 各算一份策略）
     */
    autoFightDir?: (string | null);
    /**
     * BetterGI 主程序路径
     */
    exePath?: (string | null);
};

