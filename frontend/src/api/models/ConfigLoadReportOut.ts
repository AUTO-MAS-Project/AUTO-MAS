/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConfigLoadEventOut } from './ConfigLoadEventOut';
/**
 * 单个配置文件的加载状态与规范化明细
 */
export type ConfigLoadReportOut = {
    /**
     * 配置文件名
     */
    file: string;
    /**
     * 配置文件完整路径
     */
    path: string;
    /**
     * 加载结果：ok=正常；empty=空文件按默认值；corrupt_recovered=损坏已留副本并按默认值；unreadable=文件不可读；defaulted=加载时自动纠正过配置项
     */
    status: ConfigLoadReportOut.status;
    /**
     * 读取到该状态的时间
     */
    time: string;
    /**
     * 配置文件最后写入时间；恢复备份会覆写该文件，因此该时间即恢复时间（文件不存在时为 null）
     */
    fileTime?: (string | null);
    /**
     * 损坏时保留的原文件副本路径（未损坏时为 null）
     */
    backupPath?: (string | null);
    /**
     * 本次加载中被自动纠正的配置项明细
     */
    normalizationEvents?: Array<ConfigLoadEventOut>;
};
export namespace ConfigLoadReportOut {
    /**
     * 加载结果：ok=正常；empty=空文件按默认值；corrupt_recovered=损坏已留副本并按默认值；unreadable=文件不可读；defaulted=加载时自动纠正过配置项
     */
    export enum status {
        OK = 'ok',
        EMPTY = 'empty',
        CORRUPT_RECOVERED = 'corrupt_recovered',
        UNREADABLE = 'unreadable',
        DEFAULTED = 'defaulted',
    }
}
