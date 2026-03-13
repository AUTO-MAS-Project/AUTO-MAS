/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptCreateIn = {
    /**
     * 脚本类型: MAA脚本, 通用脚本, SRC脚本, MaaEnd脚本
     */
    type: ScriptCreateIn.type;
    /**
     * 直接从该脚本ID复制创建, 仅在复制创建时使用
     */
    scriptId?: (string | null);
};
export namespace ScriptCreateIn {
    /**
     * 脚本类型: MAA脚本, 通用脚本, SRC脚本, MaaEnd脚本
     */
    export enum type {
        MAA = 'MAA',
        SRC = 'SRC',
        GENERAL = 'General',
    }
}
