/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdNativeLaunchArgs } from './ZzzOdNativeLaunchArgs';
import type { ZzzOdNativeTaskIn } from './ZzzOdNativeTaskIn';
/**
 * 直控模式：保存所选实例的原生配置（可选增量，缺省字段不写回）。
 */
export type ZzzOdNativeConfigIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标实例下标（写入其原生配置）
     */
    instanceIdx: number;
    /**
     * 账号字段名 → 值（白名单过滤；缺省不写回）
     */
    account?: (Record<string, string> | null);
    /**
     * 任务编排（顺序即执行顺序；缺省不写回）
     */
    tasks?: (Array<ZzzOdNativeTaskIn> | null);
    /**
     * 运行实例（仅运行当前/全部实例，白名单校验后写回 one_dragon.yml；缺省不写回）
     */
    instanceRun?: (string | null);
    /**
     * 游戏结束后操作（无/关闭游戏/关机，白名单校验后写回 one_dragon.yml；缺省不写回）
     */
    afterDone?: (string | null);
    /**
     * 游戏启动参数（缺省不写回）
     */
    launchArgs?: (ZzzOdNativeLaunchArgs | null);
};

