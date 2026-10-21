/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdApkInstallIn = {
    /**
     * Emulator 2.0 配置 ID
     */
    emulatorId: string;
    /**
     * 设备号, 实例必须已开机
     */
    slot: string;
    /**
     * 本机 .apk 文件的完整路径; .xapk / 拆分安装包不支持
     */
    apkPath: string;
};

