/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWProjectUpdateIn = {
    /**
     * MaaFW 脚本 ID
     */
    scriptId: string;
    /**
     * check 仅检查是否有新版本；apply 触发实际更新
     */
    action?: MaaFWProjectUpdateIn.action;
};
export namespace MaaFWProjectUpdateIn {
    /**
     * check 仅检查是否有新版本；apply 触发实际更新
     */
    export enum action {
        CHECK = 'check',
        APPLY = 'apply',
    }
}

