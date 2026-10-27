/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * MFW 项目手动更新过程 (id=<scriptId>, type=maafw.project-update.progress)
 *
 * 检查与应用两条路径共用；``stage="log"`` 只带一行新增日志，其余阶段带
 * 当前进度。速度由后端按已下载字节的时间差计算并节流，前端不必再算。
 */
export type WSMaaFWProjectUpdateProgressData = {
    /**
     * 阶段：checking / downloading / downloaded / extracting / plan_validated / staged / applying / post_validating / committed / rolled_back / completed / failed / log
     */
    stage: string;
    /**
     * running / success / failed
     */
    status: string;
    /**
     * 当前阶段的用户可读描述
     */
    message?: string;
    /**
     * 本次事件附带的新增日志行
     */
    log?: (string | null);
    /**
     * 新增日志行的级别：alert 为要用户留意的行（面板标红），普通行为 null
     */
    logLevel?: (string | null);
    /**
     * 当前阶段进度百分比（下载 / 解压 / 覆盖），未知时为 null
     */
    percent?: (number | null);
    /**
     * 已下载字节数
     */
    downloadedBytes?: (number | null);
    /**
     * 更新包总字节数，服务端未给出时为 null
     */
    totalBytes?: (number | null);
    /**
     * 下载速度 (B/s)，首个采样点为 null
     */
    speedBytesPerSec?: (number | null);
    /**
     * 更新包类型：full 全量 / incremental 增量，未知时为 null
     */
    packageKind?: (string | null);
    /**
     * 已覆盖文件数
     */
    appliedFiles?: (number | null);
    /**
     * 本次要覆盖的文件总数
     */
    totalFiles?: (number | null);
    /**
     * 解压阶段：已解压的文件数
     */
    extractedFiles?: (number | null);
    /**
     * 解压阶段：更新包里的文件总数（不含目录条目）
     */
    extractTotalFiles?: (number | null);
    /**
     * 解压阶段：已写出的字节数
     */
    extractedBytes?: (number | null);
    /**
     * 解压阶段：更新包声明的解压后总字节数
     */
    extractTotalBytes?: (number | null);
};

