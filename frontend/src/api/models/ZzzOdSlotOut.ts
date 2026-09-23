/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdSlotOwnerOut } from './ZzzOdSlotOwnerOut';
/**
 * 实例槽总览行（原生实例 / MAS 绑定槽 / 无主残留）
 */
export type ZzzOdSlotOut = {
    /**
     * 槽下标（config/{idx:02d}）
     */
    idx: number;
    /**
     * 槽类别（native=一条龙原生实例 / mas=有 MAS 用户绑定 / orphan=无主残留）
     */
    kind: ZzzOdSlotOut.kind;
    /**
     * 盘上是否已有该槽目录（只配了用户没跑过的槽没有目录）
     */
    has_dir: boolean;
    /**
     * 槽目录占用字节数（无目录为 0）
     */
    size?: number;
    /**
     * 绑定该槽的 MAS 用户（可为多个脚本）
     */
    owners?: Array<ZzzOdSlotOwnerOut>;
};
export namespace ZzzOdSlotOut {
    /**
     * 槽类别（native=一条龙原生实例 / mas=有 MAS 用户绑定 / orphan=无主残留）
     */
    export enum kind {
        NATIVE = 'native',
        MAS = 'mas',
        ORPHAN = 'orphan',
    }
}

