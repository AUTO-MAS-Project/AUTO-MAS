/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwConfig_GameInput = {
    /**
     * 账号切换方式：NONE 不切换；MAS 切换（推荐）；OKWW_SINGLE 由脚本逐账号切换、分别运行和重试；OKWW 批量切换并补跑未完成账号
     */
    AccountSwitchMethod?: ('NONE' | 'MAS' | 'OKWW_SINGLE' | 'OKWW' | null);
    /**
     * 运行前由 MAS 切换账号（仅日常任务且游戏配置启用时生效；用户未填手机号时不切换）
     */
    AccountSwitch?: (boolean | null);
    /**
     * 鸣潮启动参数（直启默认补充 -krqlv=hd，可用 -krqlv=sd 或 -krqlv=uhd 覆盖，需已安装对应资源）
     */
    Arguments?: (string | null);
    /**
     * 直启模式下手动指定的客户端程序路径（留空则由启动器路径自动定位）
     */
    ClientPath?: (string | null);
    /**
     * 是否由 MAS 管理游戏进程
     */
    Enabled?: (boolean | null);
    /**
     * 任务前是否由 MAS 检查并接管更新游戏
     */
    IfAutoUpdate?: (boolean | null);
    /**
     * 鸣潮官方启动器路径（两种启动方式均由它定位游戏安装目录）
     */
    Path?: (string | null);
    /**
     * 游戏启动方式：Client=直启客户端（资源档位默认 HD，可通过启动参数覆盖），Launcher=经官方启动器 默认值必须排首位：值非法时 correct() 回落到 options[0]
     */
    Type?: ('Client' | 'Launcher' | null);
    /**
     * 整文件同步体积上限（GB），超过则中止并提示手动处理
     */
    UpdateFullSyncLimit?: (number | null);
    /**
     * 等待游戏启动时间
     */
    WaitTime?: (number | null);
};

