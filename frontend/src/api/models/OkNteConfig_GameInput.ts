/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkNteConfig_GameInput = {
    /**
     * 运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）
     */
    AccountSwitch?: (boolean | null);
    /**
     * 游戏启动参数
     */
    Arguments?: (string | null);
    /**
     * 任务结束后是否关闭游戏
     */
    CloseOnFinish?: (boolean | null);
    /**
     * 游戏相关功能是否启用
     */
    Enabled?: (boolean | null);
    /**
     * 是否强制关闭游戏进程
     */
    IfForceClose?: (boolean | null);
    /**
     * 任务开始前是否由 MAS 启动游戏
     */
    LaunchBeforeTask?: (boolean | null);
    /**
     * 静默启动（Autoplay）= 启动器带 /autoplay 拉起，不点按钮；启动器界面启动 （LauncherUi）= 打开启动器界面，由 OCR 点「开始游戏」及其弹窗/更新分支。 默认值双轨：新建脚本取类默认 Autoplay；存量脚本（配置无该键）由 load 迁移 固化升级前的 LauncherUi（见 _migrate_oknte_launch_mode_default），保持升级前行为。
     */
    LaunchMode?: ('Autoplay' | 'LauncherUi' | null);
    /**
     * 异环直启 HTGame.exe 会卡界面，此路径为启动器 exe（NTELauncher/NTEGame.exe）， 旧值为 HTGame.exe 时运行时自动反推同安装根下的启动器
     */
    Path?: (string | null);
    /**
     * 游戏进程名称
     */
    ProcessName?: (string | null);
    /**
     * 类型: PC端, URL协议
     */
    Type?: ('Client' | 'URL' | null);
    /**
     * 自定义协议URL
     */
    URL?: (string | null);
    /**
     * 游戏等待启动时间
     */
    WaitTime?: (number | null);
};

