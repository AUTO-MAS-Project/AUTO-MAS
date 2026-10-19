/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwConfig_GameInput = {
    /**
     * 运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）
     */
    AccountSwitch?: (boolean | null);
    /**
     * 鸣潮启动参数（直启时 MAS 会额外内置 -krqlv=hd，与本参数并存）
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
     * 游戏启动方式：Client=直启客户端（内置 -krqlv=hd），Launcher=经官方启动器 默认值必须排首位：值非法时 correct() 回落到 options[0]
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

