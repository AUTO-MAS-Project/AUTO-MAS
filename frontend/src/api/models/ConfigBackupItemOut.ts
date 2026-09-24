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
     * 备份时点的配置来源三态（脚本/用户/直控）；无标注（旧版备份或未声明三态）为 null
     */
    mode?: (string | null);
};

