/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 账号组的纯接口投影。
 */
export type GameSignAccountGroupConfigInput = {
    /**
     * GameSignAccount - 云原神 combo token (DPAPI 加密)
     */
    CloudGenshinToken?: (string | null);
    /**
     * GameSignAccount - 是否启用（该用户是否参与签到）
     */
    Enabled?: (boolean | null);
    /**
     * GameSignAccount - 库街区登录凭证 (DPAPI 加密)
     */
    KuroToken?: (string | null);
    /**
     * GameSignAccount - 上次签到日期 (按用户隔离，防止重复触发)
     */
    LastSignDate?: (string | null);
    /**
     * GameSignAccount - 米游社安卓设备指纹 (DPAPI 加密，仅用于绝区零便笺)
     */
    MiyousheDeviceFp?: (string | null);
    /**
     * GameSignAccount - 米游社安卓设备 ID (DPAPI 加密，仅用于绝区零便笺)
     */
    MiyousheDeviceId?: (string | null);
    /**
     * GameSignAccount - 米游社登录凭证 (DPAPI 加密)
     */
    MiyousheToken?: (string | null);
    /**
     * GameSignAccount - 账号组名称
     */
    Name?: (string | null);
    /**
     * GameSignAccount - 森空岛登录凭证 (DPAPI 加密)
     */
    SklandToken?: (string | null);
    /**
     * GameSignAccount - 塔吉多及云异环登录凭证 (DPAPI 加密) 支持 refreshToken 纯文本或包含 cloudToken/cloudUserId 的 JSON。
     */
    TaygedoToken?: (string | null);
};

