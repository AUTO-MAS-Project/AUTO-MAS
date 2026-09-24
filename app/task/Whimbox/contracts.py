#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒（Whimbox）专项的模块内契约：PC 前台直控家族共性的四个边界。

抽象严格限定在本模块内部（L1，构造注入 + 实现侧就地兜底构造，零容器）；
命名按家族语义而非 Whimbox 字面，第二个同线专项立项时整体上提（L2）。
四个边界全是「单测需要 mock 的文件/进程 I/O」：事件流、结果判定（纯函数）、
上游配置面、无头进程。

黑箱边界与抽象正交：实现仍只复用上游 CLI 入口、只读上游结果面、只透传
上游配置格式（值经手、语义不过手）。

RPC 线预留边界（防后来人误预建）：只预留结果面——事件模型为结构化
（``WhimboxRunEvent``，非裸文本行）。上游 ``rpc_server.py`` 的 ``event.run.log``
载荷是 ``{session_id, run_id, source, message, raw_message, level, type
[, tool_call_id]}``（该推送面没写进 ``docs/protocol``，只有实现依据）：接 RPC 时
``text`` 取 ``message``、``level`` 直取，``source`` / ``type`` / ``run_id`` 进事件
上下文，不为对齐再加字段；执行模型（常驻进程/session/task.run）不预留，
Round 2 真需求时从具体实现提炼。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# ── 运行事件（结构化，RPC 结果面预留的硬约束） ─────────────────────────────


@dataclass(frozen=True, kw_only=True)
class WhimboxRunEvent:
    """运行期一条事件：v1 由日志行浅解析而来（RPC 事件面的取值约定见模块注释）。"""

    kind: str
    """事件类别：line=日志行，stopped=监控停止"""

    text: str = ""
    """事件文本（日志行原文）"""

    level: str = "info"
    """级别（对齐上游日志/RPC 推送的 level 语义；行浅解析只分 info/error）"""

    timestamp: datetime | None = None
    """行时间戳（取自日志行时间列；无时间戳的续行为 None）"""


# ── 任务目录（上游三件套的机械转换，非自建声明） ───────────────────────────


@dataclass(frozen=True, kw_only=True)
class WhimboxTaskDecl:
    """目录条目：一条龙步骤开关（上游 OneDragonDefaultSteps 键 + description）。"""

    key: str
    """上游配置键（如 step_dig），物化时的写入键"""

    display: str
    """显示名 = 上游模板 description"""

    section: str = "OneDragonDefaultSteps"
    """上游配置节"""


@dataclass(frozen=True, kw_only=True)
class WhimboxOptionDecl:
    """目录条目：一条龙目标/参数字段（上游 OneDragon 托管键）。"""

    key: str
    display: str
    section: str = "OneDragon"
    field_type: str = "text"
    """bool / int / select / multi_select / text（由模板默认值类型机械推断）"""

    options: tuple[str, ...] = field(default_factory=tuple)
    """值域（setting_options / material 派生；multi_select 为候选集）"""

    default: object = None
    """上游模板默认值（布尔语义的字符串已归一为 bool）"""


@dataclass(frozen=True, kw_only=True)
class WhimboxCatalog:
    """一次目录读取的结果：步骤开关 + 参数字段 + 上游版本提示。"""

    steps: tuple[WhimboxTaskDecl, ...] = ()
    options: tuple[WhimboxOptionDecl, ...] = ()
    upstream_version: str = ""


# ── 运行判定（纯函数，marker 表见 tools/marker.py） ────────────────────────


@dataclass(frozen=True, kw_only=True)
class WhimboxRunVerdict:
    """一次 check 的判定结果。status 语义与 AutoProxy 术语对齐。"""

    status: str
    """running / success / fatal / failed / exited_early / stalled"""

    message: str = ""
    """用户可读的状态描述（异常时为报错文案）"""

    result_block: str | None = None
    """上游「任务结果如下：」结果块原文（成功时用于报告透传）"""


# ── 四个边界 ───────────────────────────────────────────────────────────────


class IRunEventFeed(Protocol):
    """运行事件流：tail 上游日志文件并逐行转结构化事件。

    Round 2 RPC 扩展时以 ``RpcEventFeed``（订阅 ``event.run.log``）注入替换，
    高层零改动——事件模型两侧语义对齐是本契约的硬约束。
    """

    async def start(self, log_start_time: datetime) -> None:
        """开始监控（从 log_start_time 之后的行起）。"""
        ...

    async def stop(self) -> None:
        """停止监控。"""
        ...

    @property
    def latest_time(self) -> datetime:
        """最近一条带时间戳行的时间（停滞判定输入）。"""
        ...

    @property
    def log_text(self) -> str:
        """累计日志文本（marker 判定输入）。"""
        ...


class IRunResultParser(Protocol):
    """判定器：累计日志 + 进程状态 → 结构化结果（纯函数，无 I/O）。"""

    def evaluate(
        self,
        log: str,
        *,
        process_running: bool,
        stalled_minutes: float | None = None,
        stalled: bool = False,
    ) -> WhimboxRunVerdict:
        """按 marker 表判定当前状态。

        Args:
            log: 累计日志文本。
            process_running: 无头进程是否仍在运行。
            stalled_minutes: 停滞阈值（分钟），仅供拼装文案。
            stalled: 是否已停滞超时（由持有单调时钟的一方判定）。
        """
        ...


class IUpstreamConfigSurface(Protocol):
    """上游配置面：三件套元数据 + 用户覆盖集合并写入 + 快照/还原。

    实现只透传上游格式：写入键集派生自当前模板（天然落在白名单内），
    值按模板默认值类型回写（布尔字符串语义归一），不建字段映射表。
    """

    def read_catalog(self) -> WhimboxCatalog:
        """读取任务目录（上游三件套的机械转换，按 mtime 缓存）。"""
        ...

    def check_install(self) -> str | None:
        """安装哨兵检查；None=就绪，否则返回用户可操作的报错文案。"""
        ...

    def materialize_overrides(
        self,
        tasks: Mapping[str, bool],
        options: Mapping[str, object],
        *,
        run_all_accounts: bool,
    ) -> None:
        """把用户覆盖集按当前模板键集过滤后原子合并写入上游 config.json。"""
        ...

    def snapshot_pre_run(self) -> str | None:
        """运行前强制归档上游 config.json；返回归档时间戳。

        Returns:
            归档条目时间戳；指纹与最近一份相同时返回其时间戳；文件本不存在
            返回 None（还原阶段按「会话期新建」清理）。
        """
        ...

    def restore_pre_run(self, ts: str | None) -> None:
        """结束后还原运行前归档条目；ts=None 且运行前无文件时删除新建文件。"""
        ...


class IProcessLauncher(Protocol):
    """无头进程：env 构造 / 提权 spawn / 存活查询 / 终止。"""

    async def spawn(self) -> None:
        """拉起 ``python.exe -s -m whimbox.main startOneDragon``（cwd=安装根）。"""
        ...

    async def is_running(self) -> bool:
        """无头进程是否仍在运行。"""
        ...

    async def terminate(self) -> None:
        """终止无头进程（每步独立容错）。"""
        ...


__all__ = [
    "IRunEventFeed",
    "IRunResultParser",
    "IUpstreamConfigSurface",
    "IProcessLauncher",
    "WhimboxCatalog",
    "WhimboxOptionDecl",
    "WhimboxRunEvent",
    "WhimboxRunVerdict",
    "WhimboxTaskDecl",
]
