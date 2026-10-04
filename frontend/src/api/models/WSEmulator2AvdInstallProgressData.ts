/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 官方模拟器组件后台下载进度 (id=EmulatorManager, type=emulator2.avd.install.progress)
 *
 * 同一份结构也是 ``/avd/status`` 与 ``/avd/install/start`` 返回的 ``job`` 快照。
 * 下载 / 解压这类高频事件按 0.5 秒节流, 阶段切换与收尾事件必发。
 */
export type WSEmulator2AvdInstallProgressData = {
    /**
     * 下载任务 ID
     */
    jobId: string;
    /**
     * 根目录
     */
    root: string;
    /**
     * 下载源标识
     */
    source?: string;
    /**
     * 下载源名称
     */
    sourceName?: string;
    /**
     * 阶段: preparing / downloading / verifying / extracting / completed / failed / cancelled
     */
    stage: string;
    /**
     * running / success / failed / cancelled
     */
    status: string;
    /**
     * 当前阶段的用户可读描述
     */
    message?: string;
    /**
     * 当前组件标识
     */
    component?: string;
    /**
     * 当前组件名称
     */
    componentName?: string;
    /**
     * 当前是第几个组件 (从 1 起)
     */
    componentIndex?: number;
    /**
     * 本次要准备的组件数
     */
    componentCount?: number;
    /**
     * 总已下载字节数 (含续传部分)
     */
    downloadedBytes?: number;
    /**
     * 本次要下载的总字节数
     */
    totalBytes?: number;
    /**
     * 总下载进度百分比, 未知时为 null
     */
    percent?: (number | null);
    /**
     * 下载速度 (B/s), 首个采样点为 null
     */
    speedBytesPerSec?: (number | null);
    /**
     * 预计剩余秒数, 只在下载阶段给出
     */
    etaSeconds?: (number | null);
    /**
     * 当前组件的解压进度百分比, 只在解压阶段给出
     */
    extractPercent?: (number | null);
    /**
     * 失败原因, 仅 status=failed 时有值
     */
    error?: string;
    /**
     * 可选的轻量桌面没下载成功时的原因 (不影响整体成功)
     */
    launcherError?: string;
};

