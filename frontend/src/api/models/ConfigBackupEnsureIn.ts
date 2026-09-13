/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 按需归档目标池当前配置（编辑界面进入/退出时机，指纹去重）
 */
export type ConfigBackupEnsureIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标用户ID
     */
    userId: string;
    /**
     * 归档目标（取值由专项池定义）
     */
    target: string;
};

