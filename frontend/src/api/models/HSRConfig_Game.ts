/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Game = {
    /**
     * 是否由 MAS 管理游戏
     */
    Enabled?: (boolean | null);
    /**
     * 游戏路径
     */
    Path?: (string | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 等待时间（秒）
     */
    WaitTime?: (number | null);
    /**
     * 是否强制 1920x1080
     */
    ForceResolution1920x1080?: (boolean | null);
    /**
     * 仅在兑换码变化时执行兑换
     */
    RedeemCodesOnlyWhenChanged?: (boolean | null);
};

