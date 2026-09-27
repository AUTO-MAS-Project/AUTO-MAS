/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UserInfrastPlanSelectIn = {
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 脚本ID
     */
    scriptId: string;
    /**
     * 用户ID
     */
    userId: string;
    /**
     * 基建班次索引（-1=按时段自动）
     */
    index?: number;
};

