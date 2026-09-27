/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptConfigImportIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 用户ID, 未携带时导入到脚本级配置文件
     */
    userId?: (string | null);
};

