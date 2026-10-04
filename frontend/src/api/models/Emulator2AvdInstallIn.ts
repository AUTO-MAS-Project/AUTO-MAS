/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdInstallIn = {
    /**
     * 根目录, 不存在会自动创建
     */
    root: string;
    /**
     * 用户是否勾选了「我已阅读并同意」; 为 false 时拒绝下载, 后端不代为同意
     */
    acceptLicense?: boolean;
    /**
     * 下载源标识, 留空则先测速再选最快的
     */
    source?: (string | null);
    /**
     * 是否一并下载可选的轻量桌面 (Fossify Launcher)
     */
    includeLauncher?: boolean;
    /**
     * Emulator 2.0 配置 ID; 给了就在下载完成后自动把这个根目录加进该配置
     */
    emulatorId?: (string | null);
    /**
     * 自动添加时用的安装别名
     */
    alias?: (string | null);
};

