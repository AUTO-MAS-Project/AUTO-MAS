#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""托管属主登记（项目更新一侧）：哪些托管归哪个专项、它们还在不在，只经属主入口问。

项目副本（``data/mfw`` 的视图）、载荷库与预约表归项目更新这一块；托管配置归各专项。项目更新要
知道「哪些托管还在」「这个托管的来源、渠道、导入报告是什么」、要写回导入记录时，**只经各专项
登记的属主入口**，不看托管的配置类、不靠继承关系判断家族，也不拿专项的配置对象。

- **登记**：:func:`register_owner` 只记「属主名 → 取入口的办法」（一个不带参数的函数）。每次用
  之前现取；取不到（返回 None、抛异常、``owner_protocol`` 不对）就当属主没登记，记一句 warning。
  内置形态下三个专项各自登记一个（``maafw_adapter`` / ``m9a_adapter`` / ``mss_adapter``，见
  ``app/task/MaaFW/owner_entry.py``），插件化以后取入口的办法换成按服务名
  （``maafw.owner.<名字>.v1``）向插件管理器现取，调用方不用改。
- **入口的调用只传普通数据**：``list_managed()`` → :class:`OwnerListing`（是否算数 + 名下全部托管的
  :class:`ManagedRecord`），``read_managed(uid)`` → :class:`ReadResult`，``check_source_path(uid, path)``
  → :class:`PathCheck`；写回 ``write_record(uid, patch, ticket=)`` → :class:`WriteResult`（patch 是
  :class:`RecordPatch`），导入期间的锁 ``lock_managed(uid)`` / ``unlock_managed(uid, ticket)``，票据
  对外只是一个不透明的字符串。写回由属主自己校验和保存。
- **项目要求也由属主给**（可选，没实现当没有要求）：``plan_rules()`` 规则表（预览用，
  :func:`owner_plan_rules`）、``screens_projects()`` 是否只收自己那种项目、``project_mismatch(interface)``
  拒收原因（导入 / 克隆前判，:func:`owner_screens_projects` / :func:`owner_project_mismatch`）。
- **属主的回答只有在托管完整加载之后才算数**：:func:`snapshot` 的 ``require_ready=True`` 要宿主
  注入的「托管配置完整加载」信号（:func:`set_loaded_signal`）为真、至少登记了一个属主、且每个已
  登记属主都答上来、都说自己 ``ready``，有一个不满足就返回 None，据此判断「不在了」的清理整轮跳过。只做正向匹配的
  （同组候选、同来源重建的候选、原生日志清理）用 ``require_ready=False``：答不上来的属主跳过。
- 一个 uid 被两个属主同时认领时记进 :attr:`LiveSnapshot.conflicts`：清理保留，端点按类型错误拒绝。

本模块不导入任何专项，也不出现 M9A、MSS 的名字。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal

from app.task.MaaFW.tools.core.interface.plan_rules import (
    EMPTY_PLAN_RULES,
    MaaFWPlanRules,
)
from app.utils import get_logger

if TYPE_CHECKING:
    from app.task.MaaFW.tools.core.interface.models import MaaFWInterface

logger = get_logger("MFW 托管属主")

OWNER_PROTOCOL = 1
# 端点认不出托管时的原话（与原先按类型判断时一字不差）。
NOT_MAAFW_MESSAGE = "托管配置类型错误, 不是 MFW 类型"


# ---------------------------------------------------------------------------
# 入口的数据形状（普通数据）
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManagedRecord:
    """一个托管做项目操作要用的字段，全部是配置里的原值。

    ``order`` 是宿主托管列表里的位置，只用来让跨属主合起来的列表保持宿主的顺序（同组候选、同来源
    重建的候选按它排，与原先遍历托管表的先后一致）。CDK 与托管级代理原值不进 repr。
    """

    uid: str
    kind: str
    order: int
    name: Any
    source_path: Any
    report: Any
    source_version: Any
    imported_at: Any
    follow_source: bool
    channel: Any
    update_source: Any
    auto_update_mode: Any
    package_mode: Any
    proxy_address: Any = field(repr=False)
    mirror_cdk: Any = field(repr=False)
    flavor_spec: str | None
    running: bool

    @property
    def view_name(self) -> str:
        from .embedded_project import embedded_copy_dir_name

        return embedded_copy_dir_name(self.uid)

    @property
    def developer_mode(self) -> bool:
        """开着开发者模式，或项目是源码形态（与 ``follow_source_enabled`` 同一口径）。"""

        from .embedded_project import follow_source_enabled

        return follow_source_enabled(self.shape())

    @property
    def proxy_url(self) -> str:
        """更新用的代理地址：托管级优先，留空跟随全局（可能带凭据，不进日志）。"""

        from .update_credentials import resolve_update_proxy_url

        return resolve_update_proxy_url(self.shape())

    def shape(self, *, owner: str | None = None) -> ManagedShape:
        """``embedded_project`` / ``update_credentials`` 里按属性读配置的辅助函数认的只读形状。

        给了 ``owner`` 时形状上的 ``is_locked`` 每次读都经属主现问（中间隔了 await 的地方读到的是
        此刻的运行状态，与原先拿着配置对象读一致）；属主答不上来时退回这份记录里的值。
        """

        return ManagedShape(self, owner)


class ManagedShape(SimpleNamespace):
    """:meth:`ManagedRecord.shape` 的形状：``Info`` / ``Update`` / ``Embedded`` 三组原值。"""

    def __init__(self, record: ManagedRecord, owner: str | None) -> None:
        super().__init__(
            uid=record.uid,
            Info=SimpleNamespace(Name=record.name, Path=record.source_path),
            Update=SimpleNamespace(
                Source=record.update_source,
                Channel=record.channel,
                MirrorChyanCDK=record.mirror_cdk,
                AutoUpdateMode=record.auto_update_mode,
                PackageMode=record.package_mode,
                ProxyAddress=record.proxy_address,
            ),
            Embedded=SimpleNamespace(
                Report=record.report,
                SourceVersion=record.source_version,
                ImportedAt=record.imported_at,
                FollowSource=record.follow_source,
            ),
            FLAVOR_SPEC=record.flavor_spec,
        )
        object.__setattr__(self, "_record", record)
        object.__setattr__(self, "_owner", owner)

    def __repr__(self) -> str:  # CDK / 代理不进 repr
        return f"ManagedShape(uid={self.uid!r})"

    @property
    def owner_name(self) -> str | None:
        """取这份形状的属主名（写回、加锁要经它）；没绑属主为 None。"""

        return object.__getattribute__(self, "_owner")

    @property
    def is_locked(self) -> bool:
        record: ManagedRecord = object.__getattribute__(self, "_record")
        owner: str | None = object.__getattribute__(self, "_owner")
        if owner is None:
            return record.running
        return managed_running(owner, record.uid, default=record.running)


@dataclass(frozen=True, slots=True)
class OwnerListing:
    """``list_managed()`` 的回答。``ready`` 为假时整份不算数。"""

    ready: bool
    items: tuple[ManagedRecord, ...] = ()


ReadStatus = Literal["mine", "not_mine", "missing", "invalid_id"]


@dataclass(frozen=True, slots=True)
class ReadResult:
    """``read_managed(uid)`` 的回答；``detail`` 是 missing / invalid_id 时原异常的文字。"""

    status: ReadStatus
    record: ManagedRecord | None = None
    detail: str = ""


class _Unset:
    """:class:`RecordPatch` 里「这一项不写」（与「写成 None / 空串」区分开）。"""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Any = _Unset()


@dataclass(frozen=True, slots=True)
class RecordPatch:
    """要写回的项目记录；:data:`UNSET` 表示这一项不写。``report`` 是导入报告的 dict，由属主序列化。

    字段对应 ``Info.Path``、``Embedded.Report`` / ``SourceVersion`` / ``ImportedAt``、``Update.Channel``。
    """

    source_path: Any = UNSET
    report: Any = UNSET
    source_version: Any = UNSET
    imported_at: Any = UNSET
    channel: Any = UNSET


@dataclass(frozen=True, slots=True)
class WriteResult:
    """写回的结果；``reason`` 为 ``rejected``（属主拒绝，比如托管正在运行）/ ``not_found``。"""

    ok: bool
    reason: Literal["", "rejected", "not_found", "unavailable"] = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PathCheck:
    """来源路径能不能写进托管：``ok`` / ``cleared``（校验器不收、清空了）/ ``error``（附原话）。"""

    status: Literal["ok", "cleared", "error"]
    detail: str = ""


class OwnerKeyError(KeyError):
    """所有属主都说没有这个托管；``str()`` 原样给出属主那边的原话（文案与原先一字不差）。"""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


# ---------------------------------------------------------------------------
# 登记表
# ---------------------------------------------------------------------------

OwnerResolver = Callable[[], Any]

_OWNERS: dict[str, OwnerResolver] = {}
_loaded_signal: Callable[[], bool] | None = None


def register_owner(name: str, *, resolve: OwnerResolver) -> None:
    """登记一个属主：只记名字与取入口的办法。同名同参数重复登记不报错，同名换参数报错。"""

    existing = _OWNERS.get(name)
    if existing is not None and existing is not resolve:
        raise ValueError(f"重复的托管属主登记: {name}")
    _OWNERS[name] = resolve


def unregister_owner(name: str) -> None:
    _OWNERS.pop(name, None)


def registered_owners() -> tuple[str, ...]:
    return tuple(_OWNERS)


def set_loaded_signal(signal: Callable[[], bool] | None) -> None:
    """宿主注入「托管配置完整加载」的信号；没注入时据此判断「不在」的清理一律跳过。"""

    global _loaded_signal
    _loaded_signal = signal


def managed_loaded() -> bool:
    signal = _loaded_signal
    if signal is None:
        return False
    try:
        return bool(signal())
    except Exception as exc:  # noqa: BLE001 - 拿不到信号就当没加载完
        logger.warning(f"读取托管配置加载状态失败，按未加载处理：{exc}")
        return False


def _provider(name: str) -> Any | None:
    """现取属主入口；取不到就当属主没登记。"""

    resolve = _OWNERS.get(name)
    if resolve is None:
        return None
    try:
        provider = resolve()
    except Exception as exc:  # noqa: BLE001 - 属主取不到就当没登记
        logger.warning(f"托管属主 {name} 的入口取不到，按属主未登记处理：{exc}")
        return None
    if provider is None:
        logger.warning(f"托管属主 {name} 的入口不可用，按属主未登记处理")
        return None
    if getattr(provider, "owner_protocol", None) != OWNER_PROTOCOL:
        logger.warning(f"托管属主 {name} 的入口协议不符，按属主未登记处理")
        return None
    return provider


# ---------------------------------------------------------------------------
# 读：全部托管的快照
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveSnapshot:
    """一次性抄下的全部已登记属主名下的托管。

    ``by_owner`` 只含这次答上来的属主；``unavailable`` 是登记了却没答上来（取不到入口、抛异常、
    ``require_ready`` 时说自己没加载完）的。
    """

    by_owner: Mapping[str, tuple[ManagedRecord, ...]]
    unavailable: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()

    def records(self) -> list[ManagedRecord]:
        """全部托管，按宿主托管列表的顺序；被两个属主同时认领的不在其中。"""

        merged = [
            record
            for records in self.by_owner.values()
            for record in records
            if record.uid not in self.conflicts
        ]
        return sorted(merged, key=lambda record: record.order)

    def owner_of(self, uid: str) -> str | None:
        for name, records in self.by_owner.items():
            if any(record.uid == uid for record in records):
                return name
        return None

    def alive_view_names(self) -> set[str]:
        """属主确认仍在的托管（含被多个属主认领的）的视图目录名。"""

        from .embedded_project import embedded_copy_dir_name

        return {
            embedded_copy_dir_name(record.uid)
            for records in self.by_owner.values()
            for record in records
        }


def snapshot(*, require_ready: bool) -> LiveSnapshot | None:
    """抄下全部已登记属主名下的托管（同步调用，在事件循环线程上用）。

    ``require_ready=True``：托管没完整加载、一个属主都没登记、或任何一个已登记属主答不上来 / 说没
    加载完，返回 None。一个属主都没有时的空快照不算「全都不在了」：应保留集合会少掉只有来源目录、
    还没有视图的托管路径，载荷回收也会拿着空的存活来源去跑。
    """

    if require_ready and not managed_loaded():
        return None
    if require_ready and not _OWNERS:
        return None
    by_owner: dict[str, tuple[ManagedRecord, ...]] = {}
    unavailable: set[str] = set()
    for name in list(_OWNERS):
        provider = _provider(name)
        if provider is None:
            unavailable.add(name)
            continue
        try:
            listing = provider.list_managed()
        except Exception as exc:  # noqa: BLE001 - 一个属主答不上来就不算数
            logger.warning(f"托管属主 {name} 列出托管失败：{exc}")
            unavailable.add(name)
            continue
        if require_ready and not listing.ready:
            unavailable.add(name)
            continue
        by_owner[name] = tuple(listing.items)
    if require_ready and unavailable:
        return None
    seen: dict[str, str] = {}
    conflicts: set[str] = set()
    for name, records in by_owner.items():
        for record in records:
            if record.uid in seen and seen[record.uid] != name:
                conflicts.add(record.uid)
            seen.setdefault(record.uid, name)
    if conflicts:
        logger.warning(
            f"有 {len(conflicts)} 个托管同时被多个属主认领，清理时保留、端点按类型错误拒绝"
        )
    return LiveSnapshot(
        by_owner=by_owner,
        unavailable=frozenset(unavailable),
        conflicts=frozenset(conflicts),
    )


def group_members(exclude: str | None = None) -> list[Any]:
    """同组候选：除 ``exclude`` 外全部已登记属主名下的托管（事件循环线程上抄出来）。

    渠道按各自所在的组（开发者模式是它的私有渠道），运行中的标 ``busy``。
    """

    from .embedded_project import GroupMember, effective_channel

    current = snapshot(require_ready=False)
    if current is None:
        return []
    members: list[Any] = []
    for record in current.records():
        if record.uid == exclude:
            continue
        shape = record.shape()
        members.append(
            GroupMember(
                script_id=record.uid,
                channel=effective_channel(record.uid, shape),
                busy=record.running,
                name=str(record.name or ""),
                proxy_url=record.proxy_url or None,
            )
        )
    return members


def siblings() -> list[tuple[str, Any]]:
    """来源目录已删、副本又没了时可以克隆的候选：全部托管（含调用方自己）的只读形状。"""

    current = snapshot(require_ready=False)
    if current is None:
        return []
    return [(record.uid, record.shape()) for record in current.records()]


def display_name(script_id: str) -> str | None:
    """托管的名字（``Info.Name`` 原值转成字符串）；没有这个托管返回 None。"""

    try:
        _owner, record = find_managed(script_id)
    except (KeyError, ValueError, TypeError):
        return None
    return str(record.name or "")


# ---------------------------------------------------------------------------
# 读：单个托管
# ---------------------------------------------------------------------------


def find_managed(script_id: str) -> tuple[str, ManagedRecord]:
    """哪个属主名下有这个托管、它的项目记录。查单个托管不要求托管完整加载。

    - 有且只有一个属主答「是我的」：返回它；
    - 有属主说 uid 不合法：``ValueError``（原话）；
    - 答上来的属主都说没有：:class:`OwnerKeyError`（原话）；
    - 其余（不归任何已登记属主、多个属主同时认领、没有属主）：``TypeError``。

    属主入口抛出意料之外的异常时原样抛出。
    """

    mine: list[tuple[str, ManagedRecord]] = []
    invalid: str | None = None
    missing: str | None = None
    answered = 0
    missing_count = 0
    for name in list(_OWNERS):
        provider = _provider(name)
        if provider is None:
            continue
        result = provider.read_managed(str(script_id))
        answered += 1
        if result.status == "mine" and result.record is not None:
            mine.append((name, result.record))
        elif result.status == "invalid_id":
            invalid = result.detail
        elif result.status == "missing":
            missing = result.detail
            missing_count += 1
    if len(mine) == 1:
        return mine[0]
    if len(mine) > 1:
        raise TypeError(NOT_MAAFW_MESSAGE)
    if invalid is not None:
        raise ValueError(invalid)
    if answered and missing_count == answered:
        raise OwnerKeyError(missing or "")
    raise TypeError(NOT_MAAFW_MESSAGE)


def managed_running(owner: str, script_id: str, *, default: bool = False) -> bool:
    """托管此刻是否正在运行，经属主现问；答不上来时给 ``default``。"""

    provider = _provider(owner)
    if provider is None:
        return default
    try:
        result = provider.read_managed(str(script_id))
    except Exception as exc:  # noqa: BLE001 - 答不上来就沿用调用方手里的值
        logger.warning(f"托管属主 {owner} 读取托管运行状态失败：{exc}")
        return default
    if result.status != "mine" or result.record is None:
        return default
    return bool(result.record.running)


def owner_plan_rules(owner: str | None) -> MaaFWPlanRules:
    """属主给的规则表（预览用）；属主取不到或没给时是空表。"""

    provider = _provider(owner) if owner else None
    rules = getattr(provider, "plan_rules", None)
    if not callable(rules):
        return EMPTY_PLAN_RULES
    return rules()


def owner_screens_projects(owner: str | None) -> bool:
    """属主是不是只收自己那种项目（导入 / 克隆前要不要读 interface 判）；取不到属主时为假。"""

    provider = _provider(owner) if owner else None
    screens = getattr(provider, "screens_projects", None)
    return bool(screens()) if callable(screens) else False


def owner_project_mismatch(owner: str | None, interface: MaaFWInterface) -> str | None:
    """项目不是属主收的那种时的拒收原因（属主给的原话）；能收或取不到属主时为 None。

    识别本身抛的异常原样抛出，由调用方决定拦不拦。
    """

    provider = _provider(owner) if owner else None
    mismatch = getattr(provider, "project_mismatch", None)
    if not callable(mismatch):
        return None
    return mismatch(interface)


def check_source_path(owner: str, script_id: str, path: str) -> PathCheck:
    """来源路径能不能写进托管（属主按自己配置的校验器判）。会碰磁盘，调用方放进工作线程。"""

    provider = _provider(owner)
    if provider is None:
        return PathCheck("error", "托管所属的专项不可用，请稍后重试")
    return provider.check_source_path(str(script_id), path)


# ---------------------------------------------------------------------------
# 写
# ---------------------------------------------------------------------------


async def lock_managed(owner: str, script_id: str) -> str | None:
    """导入期间锁住托管（不阻塞）；拿不到返回 None。在调用方自己的 task 里直接 await。"""

    provider = _provider(owner)
    if provider is None:
        return None
    return await provider.lock_managed(str(script_id))


async def unlock_managed(owner: str, script_id: str, ticket: str) -> None:
    provider = _provider(owner)
    if provider is None:
        logger.warning(f"托管属主 {owner} 不可用，托管 {script_id} 的导入锁交不回去")
        return
    await provider.unlock_managed(str(script_id), ticket)


async def write_record(
    owner: str, script_id: str, patch: RecordPatch, *, ticket: str | None = None
) -> WriteResult:
    """写回项目记录（属主校验并保存）。不加超时：写回砍在半路比慢一点糟得多。"""

    provider = _provider(owner)
    if provider is None:
        return WriteResult(
            False, "unavailable", "托管所属的专项不可用，导入记录没有写回"
        )
    return await provider.write_record(str(script_id), patch, ticket=ticket)


async def write_or_raise(
    owner: str, script_id: str, patch: RecordPatch, *, ticket: str | None = None
) -> None:
    """:func:`write_record`，没写成就抛：被拒是 ``RuntimeError``、没有这个托管是 :class:`OwnerKeyError`。

    异常类型与文字和原先直接调 ``Config.update_script`` 时一样，调用方现有的 except 不用改。
    """

    result = await write_record(owner, script_id, patch, ticket=ticket)
    if result.ok:
        return
    if result.reason == "not_found":
        raise OwnerKeyError(result.detail)
    raise RuntimeError(result.detail)


async def write_managed_record(
    script_id: str, patch: RecordPatch, *, ticket: str | None = None
) -> None:
    """找到托管的属主再 :func:`write_or_raise`。"""

    owner, _record = find_managed(script_id)
    await write_or_raise(owner, script_id, patch, ticket=ticket)


__all__ = [
    "LiveSnapshot",
    "ManagedRecord",
    "ManagedShape",
    "NOT_MAAFW_MESSAGE",
    "OWNER_PROTOCOL",
    "OwnerKeyError",
    "OwnerListing",
    "PathCheck",
    "ReadResult",
    "RecordPatch",
    "UNSET",
    "WriteResult",
    "check_source_path",
    "display_name",
    "find_managed",
    "group_members",
    "lock_managed",
    "managed_loaded",
    "managed_running",
    "owner_plan_rules",
    "owner_project_mismatch",
    "owner_screens_projects",
    "register_owner",
    "registered_owners",
    "set_loaded_signal",
    "siblings",
    "snapshot",
    "unlock_managed",
    "unregister_owner",
    "write_managed_record",
    "write_or_raise",
    "write_record",
]
