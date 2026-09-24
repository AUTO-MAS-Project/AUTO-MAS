/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWAgentEnvPrepareIn = {
    /**
     * MFW 项目根目录，应包含 interface.json
     */
    path: string;
    /**
     * 脚本 ID，仅用于日志定位
     */
    scriptId?: (string | null);
    /**
     * 忽略指纹缓存强制重新准备，供用户手动重试使用
     */
    force?: boolean;
};

