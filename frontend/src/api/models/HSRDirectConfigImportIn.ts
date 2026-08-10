/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRDirectConfigImportIn = {
    /**
     * HSR 脚本 ID
     */
    scriptId: string;
    /**
     * HSR 用户 ID
     */
    userId: string;
    /**
     * 原生脚本引擎
     */
    engine: HSRDirectConfigImportIn.engine;
};
export namespace HSRDirectConfigImportIn {
    /**
     * 原生脚本引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}

