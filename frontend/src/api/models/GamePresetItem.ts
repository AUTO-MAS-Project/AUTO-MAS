/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GamePresetItem = {
    /**
     * 预设稳定标识
     */
    key: string;
    /**
     * 游戏展示名称
     */
    name: string;
    /**
     * 运行平台
     */
    platform: GamePresetItem.platform;
    /**
     * 预设使用的 provider
     */
    provider: string;
    /**
     * PC 可执行文件名提示
     */
    executable?: string;
    /**
     * 安卓包名
     */
    packageName?: string;
};
export namespace GamePresetItem {
    /**
     * 运行平台
     */
    export enum platform {
        PC = 'pc',
        EMULATOR = 'emulator',
    }
}

