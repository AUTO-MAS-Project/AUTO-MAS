/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Replay = {
    /**
     * 失败时保存 OBS 回放
     */
    Enabled?: (boolean | null);
    /**
     * 本机 OBS WebSocket 端口
     */
    Port?: (number | null);
    /**
     * OBS 密码，仅用于写入；省略时保留
     */
    Password?: (string | null);
    /**
     * OBS 密码是否已配置，只读
     */
    PasswordConfigured?: (boolean | null);
    /**
     * 最多保留的回放副本数
     */
    MaxReplayCount?: (number | null);
};
