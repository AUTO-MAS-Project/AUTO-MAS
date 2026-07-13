/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptRecordCreateIn = {
    /**
     * 脚本类型键
     */
    type: string;
    /**
     * 复制来源脚本 ID
     */
    scriptId?: (string | null);
    /**
     * 新建脚本时一次性写入的初始配置
     */
    initialConfig?: (Record<string, any> | null);
};

