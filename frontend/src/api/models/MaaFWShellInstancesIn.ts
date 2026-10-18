/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWShellInstancesIn = {
    /**
     * MFW 脚本 ID
     */
    scriptId: string;
    /**
     * 只扫这个目录（键位弹窗「选择其他目录」用，不写回脚本配置）；不传时先扫来源目录再扫内嵌副本
     */
    path?: (string | null);
};

