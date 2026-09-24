/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2PathItem = {
    /**
     * 路径标识
     */
    pathId: string;
    /**
     * 安装目录
     */
    installPath: string;
    /**
     * 安装别名
     */
    alias?: string;
    /**
     * 模拟器类型
     */
    type?: string;
    /**
     * 版本号
     */
    version?: string;
    /**
     * 该路径占用的设备号
     */
    slots?: Array<string>;
};

