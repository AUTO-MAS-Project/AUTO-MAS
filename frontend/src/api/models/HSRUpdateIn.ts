/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRUpdateIn = {
    /**
     * HSR 脚本配置 ID
     */
    scriptId: string;
    /**
     * 要操作的外部脚本引擎
     */
    engine: HSRUpdateIn.engine;
    /**
     * check 只查版本；apply 查完就装
     */
    action?: HSRUpdateIn.action;
};
export namespace HSRUpdateIn {
    /**
     * 要操作的外部脚本引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
    /**
     * check 只查版本；apply 查完就装
     */
    export enum action {
        CHECK = 'check',
        APPLY = 'apply',
    }
}

