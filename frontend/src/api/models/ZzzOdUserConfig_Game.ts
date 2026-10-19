/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ZzzOdUserConfig_Game = {
    /**
     * 登录账号（手机号/邮箱；留空沿用 zzz-od 已保存的登录态）
     */
    Account?: (string | null);
    /**
     * B服登录账号名
     */
    BilibiliAccountName?: (string | null);
    /**
     * 自定义窗口标题
     */
    CustomWinTitle?: (string | null);
    /**
     * DX12 启动（MAS 便捷开关：注入时把 -use-d3d12 合并进一条龙的 launch_argument_advance；上游无独立字段，勾选框是唯一权威）
     */
    Dx12?: (boolean | null);
    /**
     * 全屏模式（上游枚举原值为字符串：'0'=窗口化 '1'=全屏）
     */
    FullScreen?: ('0' | '1' | null);
    /**
     * 游戏界面语言
     */
    GameLanguage?: ('cn' | 'en' | null);
    /**
     * 游戏 exe 完整路径（ZenlessZoneZero.exe）
     */
    GamePath?: (string | null);
    /**
     * 游戏区服（zzz-od game_account.yml 的 game_region 取值）
     */
    GameRegion?: ('cn' | 'cn_b' | 'us' | 'eu' | 'asia' | 'twhkmo' | null);
    /**
     * 一条龙游戏启动参数（game.yml 六字段，照抄上游 BasicGameConfig 默认值与取值；一条龙启动游戏时消费，总开关关闭则全部不生效）： 启动参数总开关
     */
    LaunchArgument?: (boolean | null);
    /**
     * 高级参数（原样透传给一条龙拼接，上游不解析，不做 shlex 校验）
     */
    LaunchArgumentAdvance?: (string | null);
    /**
     * 显示器序号（上游枚举原值为字符串）
     */
    Monitor?: ('1' | '2' | '3' | '4' | null);
    /**
     * 登录密码（DPAPI 加密落盘，注入/回读写 game_account.yml 时经 get/set 自动加解密）
     */
    Password?: (string | null);
    /**
     * 游戏平台（上游枚举 GamePlatformEnum.PC 的真实值为大写 'PC'）
     */
    Platform?: (string | null);
    /**
     * 无边框窗口（一条龙拼参时转 -popupwindow）
     */
    PopupWindow?: (boolean | null);
    /**
     * 窗口尺寸（上游枚举原值）
     */
    ScreenSize?: ('1920x1080' | '2560x1440' | '3840x2160' | null);
    /**
     * 是否使用自定义窗口标题
     */
    UseCustomWinTitle?: (boolean | null);
};

