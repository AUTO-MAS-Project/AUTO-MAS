/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GeneralGame_info = {
    /**
     * 实例命名
     */
    name?: (string | null);
    /**
     * 是否允许并发运行
     */
    concurrent_execution?: (boolean | null);
    /**
     * 管理器或控制台路径
     */
    path?: (string | null);
    /**
     * 操作最大等待时间（秒）
     */
    max_wait_time?: (number | null);
    /**
     * ADB 程序，留空使用系统 adb
     */
    adb_path?: (string | null);
};

