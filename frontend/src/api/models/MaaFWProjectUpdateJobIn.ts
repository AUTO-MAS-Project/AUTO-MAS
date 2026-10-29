/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWProjectUpdateJobIn = {
    /**
     * MaaFW 脚本 ID
     */
    scriptId: string;
    /**
     * 为真且正在更新时，等更新结束再返回；否则立即返回当前快照
     */
    wait?: boolean;
};

