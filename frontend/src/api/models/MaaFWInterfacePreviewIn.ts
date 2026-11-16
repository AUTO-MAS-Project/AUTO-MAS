/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWInterfacePreviewIn = {
    /**
     * MaaFW 项目根目录，应包含 interface.json
     */
    path?: string;
    /**
     * 给了托管 ID 就按托管解析有效根（内嵌副本优先），忽略 path
     */
    scriptId?: (string | null);
};

