/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 配置备份条目
 */
export type ConfigBackupItemOut = {
    /**
     * 备份时间戳（目录名，如 20260910-104500）
     */
    time: string;
    /**
     * 备份时点的 base 来源（shared/independent/native）；无标注（旧版备份或未声明来源）为 null
     */
    base?: (string | null);
};

