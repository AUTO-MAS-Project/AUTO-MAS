/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ZZZ-OD 用户游戏账号配置（运行时生成 game_account.yml 注入）
 */
export type ZzzOdUserConfig_Game = {
    /**
     * 游戏区服
     */
    GameRegion?: ('cn' | 'cn_b' | 'us' | 'eu' | 'asia' | 'twhkmo' | null);
    /**
     * 游戏 exe 完整路径（ZenlessZoneZero.exe）
     */
    GamePath?: (string | null);
    /**
     * 游戏界面语言
     */
    GameLanguage?: ('cn' | 'en' | null);
    /**
     * 登录账号（留空沿用 zzz-od 已保存的登录态）
     */
    Account?: (string | null);
    /**
     * 登录密码（与 zzz-od 一致明文存储）
     */
    Password?: (string | null);
    /**
     * B服登录账号名
     */
    BilibiliAccountName?: (string | null);
    /**
     * 游戏平台（上游 GamePlatformEnum.PC 真实值为大写）
     */
    Platform?: (string | null);
    /**
     * 是否使用自定义窗口标题
     */
    UseCustomWinTitle?: (boolean | null);
    /**
     * 自定义窗口标题
     */
    CustomWinTitle?: (string | null);
    /**
     * 一条龙游戏启动参数总开关（关闭时一条龙启动游戏不带任何参数）
     */
    LaunchArgument?: (boolean | null);
    /**
     * 窗口尺寸（一条龙启动参数）
     */
    ScreenSize?: ('1920x1080' | '2560x1440' | '3840x2160' | null);
    /**
     * 全屏模式：0=窗口化 1=全屏（一条龙启动参数）
     */
    FullScreen?: ('0' | '1' | null);
    /**
     * 无边框窗口（一条龙启动参数 -popupwindow）
     */
    PopupWindow?: (boolean | null);
    /**
     * DX12 启动（注入时把 -use-d3d12 合并进一条龙高级参数，勾选框为唯一权威）
     */
    Dx12?: (boolean | null);
    /**
     * 显示器序号（一条龙启动参数）
     */
    Monitor?: ('1' | '2' | '3' | '4' | null);
    /**
     * 高级参数（原样透传给一条龙拼接，上游不解析）
     */
    LaunchArgumentAdvance?: (string | null);
};

