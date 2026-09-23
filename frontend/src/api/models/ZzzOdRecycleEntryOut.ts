/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 回收池条目（槽内容或该槽 MAS 备份池的一份快照）
 */
export type ZzzOdRecycleEntryOut = {
    /**
     * 槽下标
     */
    slot: number;
    /**
     * 条目类别（slot=槽目录快照 / mas=MAS 备份池快照）
     */
    kind: ZzzOdRecycleEntryOut.kind;
    /**
     * 快照时间戳（归档目录名）
     */
    ts: string;
    /**
     * 快照内文件数
     */
    files: number;
    /**
     * 快照占用字节数
     */
    size: number;
    /**
     * 归档目录的绝对路径（可在文件管理器打开）
     */
    path: string;
};
export namespace ZzzOdRecycleEntryOut {
    /**
     * 条目类别（slot=槽目录快照 / mas=MAS 备份池快照）
     */
    export enum kind {
        SLOT = 'slot',
        MAS = 'mas',
    }
}

