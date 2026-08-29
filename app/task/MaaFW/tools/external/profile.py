"""外壳日志画像：per-shell 的日志定位、时间戳位置与格式、完成串表（规划 2.3）。

本模块只是**数据表 + 纯函数**，不做 IO、不起进程。MFAAvalonia 条目取自
``manager.py`` 已在生产验证的常量（有测试守护两处不漂移）；MXU 条目取自
2026-08-28 对 ``D:\\MAS\\reference`` 中 MaaEnd v1.16.0-beta.1 与
MaaYYs v3.10.2 静态日志样本的审计，**尚未经真实运行验证**
（``run_validated=False``），接入 manager 运行链路前必须先完成真机验证。

静态审计要点（MXU）：

- UI 日志在 ``debug/YYYY-MM-DD-N.log``（``logs/`` 目录存在但为空），N 为当日
  启动序号，启动前无法预知——必须在外壳启动后重新解析最新序号。
- 行格式 ``YYYY-MM-DD HH:MM:SS LEVEL [Module] message``，时间戳为行首 19 字符、
  无毫秒（MFAAvalonia 为带毫秒的 1–24 字符）。
- ``kind: tasks-completed`` 与 MFAAvalonia 的「任务已全部完成！」同语义：
  **队列排空，不是成功**——样本里既出现在自然结束后，也出现在手动停止
  （``[task-stop#``）后，且一次 1 秒即结束、伴随 ``debug/on_error`` 截图的
  失败运行同样输出了它。且该行是 DEBUG 级，日志级别可配时可能缺失。
- 样本中**不存在**逐任务成功/失败结论行；MXU 的成功判定仍未解决，属真机
  验证项，此处 fail-closed 不猜测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .shell import ShellFamily

__all__ = [
    "MFAAVALONIA_LOG_PROFILE",
    "MXU_LOG_PROFILE",
    "SHELL_LOG_PROFILES",
    "ShellLogProfile",
    "get_shell_log_profile",
    "pick_latest_mxu_log",
    "resolve_log_relpath",
]

# MXU UI 日志文件名：YYYY-MM-DD-N.log，N 为当日启动序号。
_MXU_LOG_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(\d+)\.log$")


@dataclass(frozen=True)
class ShellLogProfile:
    """单个外壳家族的日志监控画像。

    ``log_relpath_strftime`` 与 ``log_glob_dir`` 恰好一个非空：前者用于
    启动前即可确定路径的外壳（MFAAvalonia），后者用于序列命名、需启动后
    再解析最新文件的外壳（MXU）。

    ``completion_markers`` 的语义是**队列排空**而非成功（两个外壳一致，
    见 manager.py 对假成功的加固注释）；``controller_failure_markers`` 为
    判别性失败标记，优先级压过排空串。
    """

    family: ShellFamily
    run_validated: bool
    time_stamp_range: tuple[int, int]
    time_format: str
    completion_markers: tuple[str, ...]
    abandon_markers: tuple[str, ...]
    controller_failure_markers: tuple[str, ...]
    # 外壳报告**某个任务**失败的串。不是终止信号——队列停不停取决于实例配置的
    # 「失败后继续」开关；它只把本轮终态从 success 降为 failed。
    failure_markers: tuple[str, ...]
    task_start_markers: tuple[str, ...]
    stop_markers: tuple[str, ...]
    # 外壳的周期性自娱自乐行：只要日志里还在滚这类行，就不能算「框架在干活」。
    # 空闲超时判定必须把它们排除，否则永远不会触发（upstream issue #388）。
    idle_noise_markers: tuple[str, ...] = ()
    # 外壳是否会在任务跑完后自行退出（MXU 的 -q / --quit-after-run）。
    # 为真时「进程干净退出」本身就是完成信号，不必依赖日志里的完成串——
    # 这对判据尚未确证的家族尤其重要。
    exits_after_run: bool = False
    # 首选日志相对路径。允许是不含 % 的固定名（strftime 原样返回）。
    log_relpath_strftime: str | None = None
    # 备选：按「日期-序号」命名的日志所在目录，首选路径不存在时回退到这里。
    log_glob_dir: str | None = None
    # 回退到 log_glob_dir 那份日志时改用的时间切片。两种命名往往出自不同
    # 版本的日志子系统，行首格式并不相同；用首选那套切片去解析回退文件会
    # 一行都对不上，LogMonitor 的 `entry_time > log_start_time` 门槛于是把
    # 整份日志当成历史全丢，表现为「外壳在跑但 MAS 一行都没读到」。
    legacy_time_stamp_range: tuple[int, int] | None = None
    legacy_time_format: str | None = None

    def __post_init__(self) -> None:
        if not self.log_relpath_strftime and not self.log_glob_dir:
            raise ValueError(
                "log_relpath_strftime 与 log_glob_dir 至少要设置一个"
            )


# 生产值来源：manager.py 的 _LOG_TIME_FORMAT / _COMPLETION_MARKERS /
# _ABANDON_MARKER / _CONTROLLER_FAILURE_MARKERS 与 log_path、LogMonitor 构造。
# 有测试逐项断言两处一致，防止任何一侧单独漂移。
MFAAVALONIA_LOG_PROFILE = ShellLogProfile(
    family=ShellFamily.MFAAVALONIA,
    run_validated=True,
    time_stamp_range=(1, 24),
    time_format="%Y-%m-%d %H:%M:%S.%f",
    completion_markers=("任务已全部完成！", "All tasks completed"),
    abandon_markers=("已放弃本次任务",),
    controller_failure_markers=("初始化控制器失败", "控制器初始化结果为空"),
    failure_markers=("任务运行失败！",),
    task_start_markers=(),
    stop_markers=(),
    # 取自真实 M9A 日志：MFA 的内存清理与热键 IPC 会稳定滚动。实测 log-20260517.log
    # 里有整段 1 小时 51 分只有这两类行的窗口——空闲超时在那段里完全被顶住。
    idle_noise_markers=("[内存管理]", "热键 IPC 客户端已连接"),
    log_relpath_strftime="logs/log-%Y%m%d.log",
)

# 静态样本证据（未经真实运行验证）：
# - 排空串：`收到 state-changed，已刷新运行时状态, kind: tasks-completed`
# - 任务开始：`[Task] 实例 <实例名>: 开始执行任务, 数量: N`
# - 任务提交：`[Task] 实例 <实例名>: 任务已提交, task_ids: [...]`
# - 手动停止：`[Task] [task-stop#<实例id>] 停止任务`
# - 控制器失败判别串：样本中未出现，不猜测，留空。
MXU_LOG_PROFILE = ShellLogProfile(
    family=ShellFamily.MXU,
    run_validated=False,
    # 当前版本（MXU@2.4.1，2026-08-29 真机采样）的行首是方括号包裹的
    # `[YYYY-MM-DD][HH:MM:SS][LEVEL][module]`，切片 [1:21] 恰好取到
    # `YYYY-MM-DD][HH:MM:SS`，故格式里保留那对括号。
    # 旧版那份无方括号的格式见下方 log_relpath_strftime 处的说明。
    time_stamp_range=(1, 21),
    time_format="%Y-%m-%d][%H:%M:%S",
    completion_markers=("kind: tasks-completed",),
    abandon_markers=(),
    controller_failure_markers=(),
    # 留空：MXU 的失败判别串尚无真机样本，不猜测（fail-closed）。MXU 的失败要靠
    # `-q` 带来的进程退出码与排空串的组合来判，见 manager 的终态分支。
    failure_markers=(),
    task_start_markers=(": 开始执行任务, 数量:",),
    stop_markers=("[task-stop#",),
    # 留空：MXU 的周期性噪音行尚无真机样本，不猜测（fail-closed）。
    idle_noise_markers=(),
    # -q / --quit-after-run：外壳跑完自行退出，进程退出即完成信号。
    exits_after_run=True,
    # 日志子系统在 MXU 2.4.1 搬了家（2026-08-29 真机比对确认）：
    #   旧版 —— 前端 webview 自己写 debug/<日期>-<序号>.log，行首无方括号，
    #           `kind: tasks-completed` 这类标记由 `[App]` 打出；
    #   新版 —— 前端日志经 tauri-plugin-log 转发给 Rust，与 `mxu_lib::*` 后端行
    #           一起追加进固定名 debug/mxu-tauri.log。
    # 同一个安装目录里两种文件会并存（旧文件是历史残留），故固定名优先、日期名回退。
    # mxu-tauri.log 是**追加型**文件，跨轮不清空；靠 LogMonitor 的
    # `entry_time > log_start_time` 门槛把上一轮的残留行挡在外面 —— 这也是上面那对
    # 时间切片必须与真机格式严格对齐的原因，切错了整轮日志会被当成历史全部丢弃。
    log_relpath_strftime="debug/mxu-tauri.log",
    log_glob_dir="debug",
    # 旧命名那份是无方括号的 `YYYY-MM-DD HH:MM:SS LEVEL [模块] ...`。
    legacy_time_stamp_range=(0, 19),
    legacy_time_format="%Y-%m-%d %H:%M:%S",
)

SHELL_LOG_PROFILES: dict[ShellFamily, ShellLogProfile] = {
    MFAAVALONIA_LOG_PROFILE.family: MFAAVALONIA_LOG_PROFILE,
    MXU_LOG_PROFILE.family: MXU_LOG_PROFILE,
}


def get_shell_log_profile(family: ShellFamily) -> ShellLogProfile | None:
    """按外壳家族取日志画像；未登记的家族返回 None（fail-closed）。"""

    return SHELL_LOG_PROFILES.get(family)


def resolve_log_relpath(profile: ShellLogProfile, now: datetime) -> str | None:
    """确定性路径外壳返回项目内相对路径；序列命名外壳返回 None。

    返回 None 表示该外壳的日志文件启动前不可预知（如 MXU 的当日启动序号），
    调用方必须在外壳启动后用 :func:`pick_latest_mxu_log` 重新解析。
    """

    if profile.log_relpath_strftime is None:
        return None
    return now.strftime(profile.log_relpath_strftime)


def pick_latest_mxu_log(names: Iterable[str], log_date: str) -> str | None:
    """在候选文件名中取指定日期（YYYY-MM-DD）序号最大的 MXU 日志名。

    纯逻辑：只比较文件名，不做 IO。无匹配返回 None。
    """

    best: tuple[int, str] | None = None
    for name in names:
        match = _MXU_LOG_NAME.match(name)
        if match is None or match.group(1) != log_date:
            continue
        sequence = int(match.group(2))
        if best is None or sequence > best[0]:
            best = (sequence, name)
    return None if best is None else best[1]
