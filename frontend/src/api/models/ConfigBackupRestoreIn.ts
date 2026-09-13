/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 把指定备份恢复到目标位置（target 取值由专项池定义）
 */
export type ConfigBackupRestoreIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标用户ID
     */
    userId: string;
    /**
     * 备份时间戳
     */
    time: string;
    /**
     * 恢复目标（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）；非法值返回 400
     */
    target: string;
};

