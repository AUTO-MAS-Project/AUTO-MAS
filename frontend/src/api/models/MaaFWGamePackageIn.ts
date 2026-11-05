/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWGamePackageIn = {
    /**
     * MaaFW 项目根目录，应包含 interface.json
     */
    path: string;
    /**
     * 要按哪个 resource 的 pipeline 推断包名
     */
    resource: string;
    /**
     * MaaFW 托管 ID；给出时按托管解析有效根（托管项目读取副本），path 只兜底
     */
    scriptId?: (string | null);
};

