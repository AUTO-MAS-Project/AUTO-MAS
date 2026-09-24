/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWEmbeddedSourceItem = {
    /**
     * 可作为克隆来源的 MFW 脚本 ID
     */
    scriptId: string;
    /**
     * 脚本名
     */
    name?: string;
    /**
     * 脚本类型（MaaFW / M9A）
     */
    type?: string;
    /**
     * 副本 interface 里的项目名
     */
    projectName?: string;
    /**
     * 副本 interface 里的版本
     */
    version?: string;
    /**
     * 源脚本正在运行，此刻不能克隆
     */
    busy?: boolean;
};

