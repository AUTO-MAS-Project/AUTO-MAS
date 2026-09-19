/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdNativeAccountField } from './ZzzOdNativeAccountField';
import type { ZzzOdNativeLaunchArgs } from './ZzzOdNativeLaunchArgs';
import type { ZzzOdNativeTaskOut } from './ZzzOdNativeTaskOut';
/**
 * 直控模式：所选实例的完整原生配置（账号字段 + 任务编排 + 运行实例）。
 */
export type ZzzOdNativeConfigOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 当前选择的实例下标
     */
    instanceIdx: number;
    /**
     * 实例名称
     */
    instanceName: string;
    /**
     * 账号配置字段（game_account.yml）
     */
    account: Array<ZzzOdNativeAccountField>;
    /**
     * 任务编排（app_id/enabled/顺序，与目录合并后的可选项）
     */
    tasks: Array<ZzzOdNativeTaskOut>;
    /**
     * 运行实例（one_dragon.yml instance_run 原值：仅运行当前/全部实例）
     */
    instanceRun: string;
    /**
     * 游戏启动参数（game.yml，缺失字段合并上游默认值）
     */
    launchArgs?: (ZzzOdNativeLaunchArgs | null);
};

