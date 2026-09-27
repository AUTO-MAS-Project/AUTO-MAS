/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UserSetIn = {
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
     * 用户ID
     */
    userId: string;
    /**
     * JSON文件路径, 用于导入自定义基建文件
     */
    jsonFile: string;
};

