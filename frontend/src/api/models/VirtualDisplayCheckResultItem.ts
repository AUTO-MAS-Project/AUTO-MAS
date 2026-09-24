/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 检测的三段之一。分开报是有意的：给用户的下一步动作完全不同。
 */
export type VirtualDisplayCheckResultItem = {
    /**
     * 检测阶段
     */
    stage: VirtualDisplayCheckResultItem.stage;
    /**
     * 该阶段是否通过
     */
    passed: boolean;
    /**
     * 面向用户的说明
     */
    message: string;
};
export namespace VirtualDisplayCheckResultItem {
    /**
     * 检测阶段
     */
    export enum stage {
        INSTALLED = 'installed',
        OPENABLE = 'openable',
        EFFECTIVE = 'effective',
    }
}

