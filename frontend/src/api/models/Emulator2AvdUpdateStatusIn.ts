/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateStatusIn = {
    /**
     * 魔改 AVD 根目录; 必须已加进 Emulator 2.0, 别的目录一律拒绝
     */
    root: string;
    /**
     * 先强制查一次最新版本 (界面上的「检查更新」; 不走缓存, 不带 CDK); 查不到不算失败, 原因写在 checkError
     */
    check?: boolean;
};

