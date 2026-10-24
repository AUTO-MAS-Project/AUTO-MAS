/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateIn = {
    /**
     * 魔改 AVD 根目录; 必须已加进 Emulator 2.0, 别的目录一律拒绝
     */
    root: string;
    /**
     * 有实例开着时, 换上前先关掉它们 (安卓正常关机, 不行再 sync + kill, 不硬杀); 为 false 时不动手, 只返回要关几台
     */
    closeInstances?: boolean;
};

