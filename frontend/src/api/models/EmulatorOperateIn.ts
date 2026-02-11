/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EmulatorOperateIn = {
    /**
     * 模拟器 ID
     */
    emulatorId: string;
    /**
     * 操作类型
     */
    operate: EmulatorOperateIn.operate;
    /**
     * 模拟器索引
     */
    index: string;
};
export namespace EmulatorOperateIn {
    /**
     * 操作类型
     */
    export enum operate {
        OPEN = 'open',
        CLOSE = 'close',
        SHOW = 'show',
    }
}

