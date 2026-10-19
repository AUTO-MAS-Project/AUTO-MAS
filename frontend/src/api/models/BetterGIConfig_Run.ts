/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BetterGIConfig_Run = {
    /**
     * 账号切换方式（脚本级，参考 MaaEnd Run.AccountSwitchMethod）： BGI = BetterGI「切换账号多模式」脚本执行（国际服请改用此方式）；MAS = MAS 侧 前台 OCR 直接操控游戏切号（官服/B服，游戏由 MAS 托管启动），官服/B服推荐。 默认值双轨：新建脚本取类默认 MAS；存量脚本（配置无该键）由 load 迁移固化 旧默认 BGI（见 _migrate_bgi_account_switch_default），保持升级前行为。
     */
    AccountSwitchMethod?: ('BGI' | 'MAS' | null);
    /**
     * 单账号运行总时限（分钟），包含等待和全部重试
     */
    HardTimeLimit?: (number | null);
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 日志超时限制
     */
    RunTimeLimit?: (number | null);
    /**
     * 重试次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 是否以管理员权限启动 BetterGI。默认提权（贴近旧行为）；若 MAS 平时以非管理员 运行、又不希望每次启动 BGI 都弹 UAC（无人值守任务尤其容易挂在授权上），可关闭。 MAS 自身已提权时，即使此处开启，也不会重复触发 UAC（子进程自动继承管理员令牌）。
     */
    UseAdmin?: (boolean | null);
};

