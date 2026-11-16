/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MSSConfig_GameInput = {
    /**
     * 游戏启动参数，仅 DirectExe 模式使用；URL 模式的参数写进链接
     */
    Arguments?: (string | null);
    /**
     * AttachOnly 模式下结束后谁关游戏：Script 交给脚本（MAS 不关）；OnFailure 本次运行没正常完成（失败、超时、停止、异常）时由 MAS 关；Always 结束后一律由 MAS 关。MAS 只关本次运行开始之后才出现的进程，重试之间不关。DirectExe 与 URL 模式忽略它
     */
    CloseMode?: ('Script' | 'OnFailure' | 'Always' | null);
    /**
     * 托管级键位（PI v2.8 hotkey 选项）：``{option 名: {字段名: 组合键字符串}}``， 组合键写成「修饰键+…+主键」（如 ``"Ctrl+E"``）。只存与 interface 默认不同的 字段；运行时叠加到每个任务实际生效的 hotkey 选项上，盖过账号快照 / 预设里的值。 仅 Win32 控制器生效（Adb 等其他控制器不叠加）。interface 里已没有的 option / 字段静默忽略，映射不了的值告警后回落到快照 / 默认值（runner/run_plan.py）。
     */
    Hotkeys?: (string | null);
    /**
     * 游戏生命周期模式：DirectExe 由 MAS 按 exe 启动、结束后关闭；URL 由 MAS 打开链接拉起游戏、结束后关闭；AttachOnly 由脚本或用户自己启动，MAS 只接管窗口，结束后是否由 MAS 关闭见 CloseMode
     */
    LaunchMode?: ('DirectExe' | 'URL' | 'AttachOnly' | null);
    /**
     * 游戏 exe：DirectExe 模式下 MAS 启动它；URL 模式下必填，用来认出游戏（是否已在运行、等窗口、关闭、Unity 分辨率）；AttachOnly 模式下可选，用来认出要关闭的游戏
     */
    LaunchPath?: (string | null);
    /**
     * AttachOnly 模式下可选的启动器 exe，MAS 兜底关闭游戏时一并关闭本次运行期间打开的启动器
     */
    LauncherPath?: (string | null);
    /**
     * 安卓游戏包名，Adb controller 用：启动模拟器时顺带把游戏拉起来。 留空表示从项目的 pipeline 里自动识别（见 embedded/game_package.py）； 自动识别是启发式的，填了这里就以这里为准。识别不出且没填则不启动游戏。
     */
    PackageName?: (string | null);
    /**
     * URL 模式下 MAS 打开的链接，如 steam://rungameid/<appid>
     */
    URL?: (string | null);
    /**
     * DirectExe 与 URL 模式下，启动游戏前按 exe 路径反查 Unity 注册表，临时把分辨率改成所选 尺寸的窗口模式，游戏关闭后恢复原值（tools/embedded/game_resolution.py）。 只对 Unity 引擎的游戏有效；游戏已在运行时不改。Off 表示不碰。
     */
    UnityResolution?: ('Off' | '1920x1080' | '1280x720' | null);
    /**
     * 游戏启动等待时间（秒）：既是等窗口出现的上限，也是窗口出现后等画面稳定的上限。 Unity 游戏窗口出现时还在黑屏加载，登录界面往往要二三十秒后才渲染出来； MaaEnd 的 SceneManager 见连续画面不变十几秒就判「环境识别异常」直接失败。 等画面时 worker 每秒截一帧，有内容且连续几秒不变就提前下发，等不到才等满； MaaFW 初始化（加载资源、连 controller、起 agent）与之重叠而不是干等。 只对本轮由 MAS 拉起的游戏生效，AttachOnly 与「游戏已在运行」不等画面。
     */
    WaitTime?: (number | null);
};

