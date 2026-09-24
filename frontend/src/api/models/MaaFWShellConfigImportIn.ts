/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWShellConfigImportIn = {
    /**
     * MFW 脚本 ID（项目来源目录从它取）
     */
    scriptId?: (string | null);
    /**
     * 没有脚本时兜底的项目目录
     */
    path?: string;
    /**
     * 要导入的外壳实例 ID
     */
    instanceId: string;
};

