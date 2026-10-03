/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWAgentEnvPrepareIn = {
    /**
     * MFW 项目根目录，应包含 interface.json
     */
    path?: string;
    /**
     * 脚本 ID；内嵌脚本按它解析副本目录，此时 path 可留空
     */
    scriptId?: (string | null);
    /**
     * 忽略指纹缓存强制重新准备，供用户手动重试使用
     */
    force?: boolean;
};

