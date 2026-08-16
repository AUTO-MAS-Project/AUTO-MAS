/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRDirectConfigImportData = {
    /**
     * 原生脚本引擎
     */
    engine: HSRDirectConfigImportData.engine;
    /**
     * 配置来源
     */
    source?: (string | null);
    /**
     * 导入时间
     */
    imported_at?: (string | null);
    /**
     * 快照字节数
     */
    size?: number;
};
export namespace HSRDirectConfigImportData {
    /**
     * 原生脚本引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}

