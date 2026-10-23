/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateOptionsIn = {
    /**
     * 魔改 AVD 根目录; 必须已加进 Emulator 2.0, 别的目录一律拒绝
     */
    root: string;
    /**
     * 空闲时自动装: 任务都结束、实例全关时才装 (任务跑完后或 MAS 启动时), 默认关
     */
    autoInstall: boolean;
};

