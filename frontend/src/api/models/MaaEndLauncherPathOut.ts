/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * MaaEnd 启动器路径识别结果（供前端自动识别与落盘）
 */
export type MaaEndLauncherPathOut = {
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
     * 由游戏客户端路径识别到的启动器 Launcher.exe 完整路径
     */
    launcher_path: string;
};

