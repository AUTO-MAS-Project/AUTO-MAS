/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2InstanceCreateIn = {
    /**
     * 配置ID
     */
    emulatorId: string;
    /**
     * 在哪条模拟器安装下新建
     */
    pathId: string;
    /**
     * 新实例名称, 留空由模拟器自己命名
     */
    name?: (string | null);
};

