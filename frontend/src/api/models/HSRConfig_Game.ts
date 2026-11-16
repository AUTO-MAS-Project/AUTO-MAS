/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Game = {
    /**
     * 是否由 MAS 管理游戏启停、进程监测和窗口操作（仅客户端平台）
     */
    Enabled?: (boolean | null);
    /**
     * 启动游戏时临时覆盖 1920×1080 注册表分辨率
     */
    ForceResolution1920x1080?: (boolean | null);
    /**
     * 游戏路径
     */
    Path?: (string | null);
    /**
     * 游戏平台：本地客户端 / 云·星穹铁道（MAS 托管浏览器，只用三月七）。 OptionsValidator.correct() 回退的是 options[0]，Client 必须排第一。
     */
    Platform?: ('Client' | 'Cloud' | null);
    /**
     * 仅在原生兑换码内容变化时执行兑换
     */
    RedeemCodesOnlyWhenChanged?: (boolean | null);
    /**
     * 等待时间（秒）
     */
    WaitTime?: (number | null);
};

