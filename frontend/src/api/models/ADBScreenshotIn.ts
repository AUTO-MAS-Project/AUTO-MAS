/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ADBScreenshotIn = {
    /**
     * ADB 可执行文件的路径
     */
    adb_path: string;
    /**
     * 设备序列号，格式如 '127.0.0.1:5555' 或 'emulator-5554'
     */
    serial: string;
    /**
     * 是否使用 screencap PNG 方法，False 时使用 screencap raw 方法
     */
    use_screencap?: boolean;
};

