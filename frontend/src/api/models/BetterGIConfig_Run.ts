/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * BetterGI 运行配置（通用字段 + BetterGI 专属字段）
 */
export type BetterGIConfig_Run = {
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 重试次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 日志超时限制
     */
    RunTimeLimit?: (number | null);
    /**
     * 是否以管理员权限启动 BetterGI（MAS 未提权时开启会触发 UAC）
     */
    UseAdmin?: (boolean | null);
    /**
     * 账号切换方式: BGI=BetterGI「切换账号多模式」脚本执行; MAS=MAS 前台直接操控游戏切号（官服/B服，游戏由 MAS 托管启动）
     */
    AccountSwitchMethod?: ('BGI' | 'MAS' | null);
};

