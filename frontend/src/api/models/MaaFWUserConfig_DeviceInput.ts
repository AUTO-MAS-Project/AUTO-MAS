/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWUserConfig_DeviceInput = {
    /**
     * 当前用户覆盖 ADB 地址，留空时使用脚本级模拟器配置
     */
    AdbAddress?: (string | null);
    /**
     * Win32 / Gamepad 窗口句柄，0 表示未指定
     */
    HWnd?: (number | null);
    /**
     * PlayCover 地址
     */
    PlayCoverAddress?: (string | null);
    /**
     * PlayCover UUID
     */
    PlayCoverUuid?: (string | null);
};

