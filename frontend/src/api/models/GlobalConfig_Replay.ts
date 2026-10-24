/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Replay = {
    /**
     * 连接已运行的 OBS，在自动代理最终失败时保存回放。
     */
    Enabled?: (boolean | null);
    /**
     * 历史视频容量上限（MiB），仅回收历史视频，不清理 OBS 原文件。
     */
    VideoStorageLimitMiB?: (number | null);
    /**
     * OBS 认证密码按现有敏感配置规则加密落盘。
     */
    Password?: (string | null);
    /**
     * OBS WebSocket 仅连接本机。
     */
    Port?: (number | null);
    /**
     * OBS 密码是否已配置，只读
     */
    readonly PasswordConfigured?: (boolean | null);
};

