/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2DevicesIn = {
    /**
     * 配置ID
     */
    emulatorId: string;
    /**
     * 是否连四项设置与稳定模式一起读; 状态轮询传 false, 只取在线状态与 ADB 地址
     */
    withSettings?: boolean;
};

