/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * MCP 的 HTTP 快照与 WS 进度共用契约；revision 在同一进程内单调递增。
 */
export type McpStatusData = {
    enabled: boolean;
    state: McpStatusData.state;
    stage: ('importing' | 'building' | 'validating' | 'mounting' | null);
    startedAt: (string | null);
    finishedAt: (string | null);
    elapsedMs: number;
    toolCount: number;
    error: ('import_failed' | 'build_failed' | 'validation_failed' | 'mount_failed' | 'cleanup_failed' | null);
    /**
     * 后端进程标识；重启后 revision 重新开始
     */
    instanceId: string;
    /**
     * 加载尝试标识，显式重试时更换
     */
    runId: string;
    revision: number;
};
export namespace McpStatusData {
    export enum state {
        SKIPPED = 'skipped',
        PENDING = 'pending',
        RUNNING = 'running',
        READY = 'ready',
        FAILED = 'failed',
        CANCELLED = 'cancelled',
    }
}

