/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Backup = {
    /**
     * 版本号变化后的首次启动是否自动备份数据
     */
    IfAutoBackup?: (boolean | null);
    /**
     * 自动备份目录
     */
    BackupDir?: (string | null);
    /**
     * 上次运行记录的版本号
     */
    LastVersion?: (string | null);
};

