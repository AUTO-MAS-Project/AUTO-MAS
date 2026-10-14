/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCultivateImportSkippedItem = {
    /**
     * 可本地化的导入错误类型
     */
    error: MaaCultivateImportSkippedItem.error;
    /**
     * 跳过条目的序号，从 1 开始
     */
    index: number;
    /**
     * 跳过条目的干员名称
     */
    name?: string;
};
export namespace MaaCultivateImportSkippedItem {
    /**
     * 可本地化的导入错误类型
     */
    export enum error {
        FORMAT = 'format',
        EMPTY = 'empty',
        OPERATOR = 'operator',
        AMBIGUOUS = 'ambiguous',
        ELITE = 'elite',
        SKILL = 'skill',
        MASTERY = 'mastery',
        UNSUPPORTED = 'unsupported',
    }
}

