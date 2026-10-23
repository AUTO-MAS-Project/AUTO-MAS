/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdInstallIn = {
    /**
     * 要装进去的文件夹: 空文件夹 (下载 ModAVD 再补全组件), 或已经解压好、只缺组件的魔改 AVD 根目录
     */
    root: string;
    /**
     * 用户已在界面上阅读并同意《Android SDK 许可协议》; 为 false 时拒绝
     */
    acceptLicense?: boolean;
};

