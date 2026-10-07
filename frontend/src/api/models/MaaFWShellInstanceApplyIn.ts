/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWShellInstanceApplyIn = {
    /**
     * MFW 脚本 ID
     */
    scriptId: string;
    /**
     * 要覆盖任务队列的用户 ID
     */
    userId: string;
    /**
     * 从哪份外壳实例导入
     */
    instanceId: string;
    /**
     * 实例从哪个目录列出来的就传哪个（弹窗「选择其他目录」选的）；不传时先来源目录再内嵌副本，与列表同一口径
     */
    path?: (string | null);
};

