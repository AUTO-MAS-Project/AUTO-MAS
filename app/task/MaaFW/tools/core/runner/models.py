from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.task.MaaFW.tools.core.agent_env.models import (
    MaaFWAgentCommandPlan,
)

MaaFWControllerType = Literal["Adb", "Win32"]
# 项目节点 attach.auto_mas 声明的联动信号（见 run_signal.py）。取值就是
# worker_protocol.SERVER_MAINTENANCE / CLIENT_UPDATE_REQUIRED：Literal 里只能写字面量（类型检查器
# 不认变量），改那边时这里一起改。
MaaFWRunSignal = Literal["server_maintenance", "client_update_required"]


class MaaFWResolvedPath(BaseModel):
    raw: str
    resolved: str
    exists: bool
    isFile: bool = False
    isDir: bool = False


class MaaFWResourceBundlePlan(BaseModel):
    name: str
    label: str | None = None
    paths: list[MaaFWResolvedPath] = Field(default_factory=list)
    attachedPaths: list[MaaFWResolvedPath] = Field(default_factory=list)
    # interface 里 resource.hash（PI v2.6.0）：只加载 paths 之后 MaaResourceGetHash 应得的值。
    # worker 在加载 attachedPaths 之前比对，不一致只告警。
    hash: str | None = None


class MaaFWTaskRunPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str
    options: dict[str, Any] = Field(default_factory=dict)
    pipelineOverride: dict[str, Any] = Field(default_factory=dict)
    logOptions: dict[str, Any] = Field(default_factory=dict)
    overrideNodes: list[str] = Field(default_factory=list)
    # 与 interface 里 default_case 不同的选项，键值都已换成给人看的标签并脱敏；
    # 建计划时算好，runner 只负责拼成一行。
    nonDefaultOptions: dict[str, Any] = Field(default_factory=dict)
    # 特调声明的关键任务（如 M9A 的切换账号）：失败或超时就结束本轮、报这句，由宿主照常
    # 重试；None 是普通任务，失败后继续后面的任务。
    abortRoundMessage: str | None = None
    # 特调声明的收尾任务（如 M9A 的关闭游戏）：失败、超时或原地打转都照常截图并写一行日志
    # （接上这句说明），但不计入本轮失败、不触发重试；None 是普通任务。
    nonFatalMessage: str | None = None


class MaaFWSkippedTaskPlan(BaseModel):
    name: str
    label: str | None = None
    entry: str | None = None
    reason: str


class MaaFWPretaskRunPlan(BaseModel):
    name: str
    label: str | None = None
    executable: str
    args: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class MaaFWRunPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    projectName: str
    projectLabel: str | None = None
    controllerName: str
    controllerType: str
    # interface 里该 controller 的截图缩放声明（display_short_side / display_long_side /
    # display_expand / display_raw 原样摘出），worker 建控制器后按它设截图目标尺寸。
    controllerDisplay: dict[str, Any] = Field(default_factory=dict)
    resourceName: str
    resource: MaaFWResourceBundlePlan
    nativePluginPaths: list[MaaFWResolvedPath] = Field(default_factory=list)
    agents: list[MaaFWAgentCommandPlan] = Field(default_factory=list)
    pretasks: list[MaaFWPretaskRunPlan] = Field(default_factory=list)
    piEnv: dict[str, str] = Field(default_factory=dict)
    tasks: list[MaaFWTaskRunPlan] = Field(default_factory=list)
    skippedTasks: list[MaaFWSkippedTaskPlan] = Field(default_factory=list)
    # 用户的全局选项表（已解密、叠过脚本级键位），各任务覆盖里全局那一层的取值。任务的
    # options 是给人看的合并结果，同一选项任务自己也有值时看不到这一层，宿主给日志打码时两处都收。
    globalOptions: dict[str, Any] = Field(default_factory=dict)
    # 建计划时降级处理的项（例如没设的快捷键被跳过），宿主写进用户可见的运行日志。
    warnings: list[str] = Field(default_factory=list)
    # 项目 zh_cn 语言文件的内容，worker 用它翻译 pipeline focus 文案里的 ``$key``。
    # 随计划带进 worker，runner 自己不再读语言文件。
    i18n: dict[str, Any] = Field(default_factory=dict)


class MaaFWDeviceConfig(BaseModel):
    type: MaaFWControllerType
    adbPath: str | None = None
    address: str | None = None
    hWnd: int | None = None
    screencapMethods: int = 0
    inputMethods: int = 0
    screencapMethod: int = 0
    mouseMethod: int = 0
    keyboardMethod: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    # 等待 adb 认出设备的秒数。冷启动的模拟器在 open() 返回后往往还要一段时间
    # adbd 才起来；宿主按该模拟器的 Info.MaxWaitTime 下发，缺省时用 runner 常量。
    adbReadyTimeout: int | None = None
    # 模拟器进程号（宿主从模拟器管理器的 open 结果里取，目前只有魔改 AVD 给）。等 adb 期间
    # 进程没了就立即判失败，交给外层重试重开模拟器，而不是把整段等待预算耗完。
    emulatorPid: int | None = None
    # 该进程的启动时刻（Unix 秒）。和进程号一起比对：进程号被复用给别的进程时也算已退出。
    emulatorStartedAt: float | None = None


class MaaFWFailureScreenshot(BaseModel):
    task: str
    path: str


class MaaFWResourceFailure(BaseModel):
    """资源包没能加载：``load_failed`` 是 MaaFramework 拒收了这个资源包（节点重名、JSON 写错
    之类，原因只在原生 ERR 行里），``missing`` 是资源目录本身不在。``path`` 是计划里解析出
    的资源包目录。两种都是每次尝试都一样，宿主据此不重启游戏 / 模拟器重试。"""

    kind: Literal["load_failed", "missing"]
    path: str


class MaaFWRunResult(BaseModel):
    success: bool
    projectName: str
    controllerName: str
    resourceName: str
    completedTasks: list[str] = Field(default_factory=list)
    failedTask: str | None = None
    errorMessage: str | None = None
    # 给用户看的完整失败摘要；诊断与环境故障判定仍使用 errorMessage。
    userMessage: str | None = None
    # 任务失败当刻的画面，按失败先后排列；宿主把它们塞进通知。
    failureScreenshots: list[MaaFWFailureScreenshot] = Field(default_factory=list)
    # 到了 runDeadlineAt 由 worker 自己停下来的：宿主据此在重试前重启游戏/模拟器。
    # 和 errorMessage 分开放，宿主不必靠匹配文案判断。
    timedOut: bool = False
    # 项目声明的信号节点命中（停服维护 / 需要更新客户端），worker 已主动停下、跳过本轮剩余
    # 任务。与 timedOut 同理单独成字段，宿主据此分流，不靠文案判断。
    signal: MaaFWRunSignal | None = None
    signalNode: str | None = None
    # 初始化时资源包没能加载（见 MaaFWResourceFailure）。与 timedOut / signal 同理单独成字段，
    # 宿主据此不重试、去原生 ERR 行里找原因，不靠匹配「加载资源失败」的文案。
    resourceFailure: MaaFWResourceFailure | None = None


class MaaFWRunnerJobPayload(BaseModel):
    plan: MaaFWRunPlan
    deviceConfig: MaaFWDeviceConfig
    # 并入自 mfwa：宿主进程身份，worker 据此看门狗自杀，避免宿主崩溃后留下孤儿
    # 进程继续占用设备。createTime 与 pid 配对使用，防 pid 复用误判。
    ownerPid: int | None = None
    ownerCreateTime: float | None = None
    # 任务失败截图落盘目录与文件名前缀，宿主指向本次运行的 history 目录，
    # 让截图和 .log / .maafw.log 挨在一起。None 表示不截。
    failureScreenshotDir: str | None = None
    failureScreenshotPrefix: str = ""
    # 第一个任务最早可下发的墙钟时刻（time.time() 秒）。宿主刚拉起桌面游戏时窗口
    # 虽已出现、画面还没渲染出来，worker 把资源加载、连 controller、起 agent 都
    # 做完后再等到这个点，而不是在宿主里干等。None 表示不等。
    taskStartNotBefore: float | None = None
    # 首个任务前怎么判断游戏已就绪：screen 按画面提前放行（默认）；disk_quiet 要画面有内容
    # 且客体读盘停下来（runner._wait_task_start_disk_quiet）。宿主决定用哪种。
    taskStartGateMode: str = "screen"
    # 单次运行的截止墙钟时刻（time.time() 秒）。到点 worker 自己停掉当前任务、
    # 截一张图再把结果发回来，宿主只在 worker 没能及时停下时才强杀。None 表示不限。
    runDeadlineAt: float | None = None
    # 单个任务的时限（秒）。到点只停这一个任务、截一张超时图，记一条任务失败再继续后面的
    # 任务（计划里第一个任务超时则结束本轮）；None / 0 表示不限。宿主按 Run.TaskTimeLimit
    # 换算后随 job 文件下发。
    taskTimeLimitSeconds: int | None = None
    # 按任务名覆盖的单任务时限（秒），键是 MaaFWTaskRunPlan.name；值 0 表示该任务不限。
    taskTimeLimitOverrides: dict[str, int] | None = None
    # 原地打转检测（实验性）：任务在短周期里反复执行同一串节点、识别结果又不变时停掉它，
    # 收尾与单任务超时同一口径。宿主按 Run.LoopGuard 下发，默认关。
    loopGuard: bool = False
    # 宿主的事件通道（worker_protocol.WorkerEventServer.spec：命名管道名 / 一次性令牌）。
    # 宿主写 job 时填（worker_protocol.encode_job）；None 时 worker 把事件写 stdout（旧格式）。
    eventChannel: dict[str, Any] | None = None
