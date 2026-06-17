/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 单个三深渊快照的导入结果摘要
 */
export type AbyssSnapshotImportItem = {
    /**
     * 深渊快照键: ForgottenHall / PureFiction / Apocalyptic
     */
    snapshotKey: string;
    /**
     * 是否成功从 M7A config.yaml 读取并写入
     */
    success: boolean;
    /**
     * 关卡范围（[min, max]），缺失时为 None
     */
    level?: null;
    /**
     * 快照中包含的队伍字段，如 team1/team2/team3
     */
    teamKeys?: Array<string>;
    /**
     * 错误描述（导入失败时）
     */
    error?: (string | null);
};
