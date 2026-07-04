#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class _Waiter:
    """保存一个等待依赖满足后执行的回调任务。

    Args:
        owner (str): 回调所属实例 ID。
        needs (set[str]): 硬依赖服务名集合。
        wants (set[str]): 软依赖服务名集合。
        ready (Callable[[], Any]): 依赖满足时执行的回调。
    """

    owner: str
    needs: set[str]
    wants: set[str]
    ready: Callable[[], Any]


class ServiceRegistry:
    """管理服务声明、赋值、依赖绑定和动态注入回调。"""

    def __init__(self) -> None:
        """初始化服务注册中心的内部索引结构。"""
        self._declared: set[str] = set()
        self._owners: Dict[str, set[str]] = {}
        self._values: Dict[str, Dict[str, Any]] = {}
        self._needs: Dict[str, set[str]] = {}
        self._wants: Dict[str, set[str]] = {}
        self._waiters: list[_Waiter] = []
        self._before: list[Callable[[str, set[str]], Any]] = []
        self._after: list[Callable[[str, set[str]], Any]] = []

    @staticmethod
    def _names(raw: Any) -> set[str]:
        """将任意输入归一化为服务名集合。

        Args:
            raw (Any): 原始输入值。

        Returns:
            set[str]: 过滤空白后的服务名集合。
        """
        if raw is None:
            return set()
        if isinstance(raw, str):
            name = raw.strip()
            return {name} if name else set()
        if isinstance(raw, (list, tuple, set)):
            names: set[str] = set()
            for item in raw:
                text = str(item or "").strip()
                if text:
                    names.add(text)
            return names
        return set()

    def watch(self, kind: str, func: Callable[[str, set[str]], Any]) -> None:
        """注册服务变化监听器到 before 或 after 通道。

        Args:
            kind (str): 监听阶段，支持 before 或 after。
            func (Callable[[str, set[str]], Any]): 监听回调函数。

        Raises:
            ValueError: 当 kind 不是 before 或 after 时抛出。
        """
        slot = str(kind or "").strip().lower()
        if slot == "before":
            self._before.append(func)
            return
        if slot == "after":
            self._after.append(func)
            return
        raise ValueError("kind 仅支持 before 或 after")

    def provide(self, name: str, owner: str) -> None:
        """声明某实例可提供指定服务但不写入服务值。

        Args:
            name (str): 服务名。
            owner (str): 提供者实例 ID。

        Raises:
            ValueError: 当服务已被其他实例声明时抛出。
        """
        service = str(name or "").strip()
        who = str(owner or "").strip()
        if not service or not who:
            return

        existing = self._owners.get(service)
        if existing:
            if who in existing:
                return
            owners = ",".join(sorted(existing))
            raise ValueError(
                f"服务名重复注册: service={service}, owner={who}, existing={owners}"
            )

        self._declared.add(service)
        self._owners[service] = {who}

    def set(self, name: str, value: Any, owner: str) -> None:
        """写入服务值并按 before/after 顺序发布变化通知。

        Args:
            name (str): 服务名。
            value (Any): 服务实例值。
            owner (str): 提供者实例 ID。
        """
        service = str(name or "").strip()
        who = str(owner or "").strip()
        if not service or not who:
            return

        self.provide(service, who)
        users = self.users(service)
        self._emit(self._before, service, users)
        self._values.setdefault(service, {})[who] = value
        self._emit(self._after, service, users)
        self._flush()

    def bind(self, owner: str, needs: Any = None, wants: Any = None) -> None:
        """绑定实例的硬依赖和软依赖声明。

        Args:
            owner (str): 实例 ID。
            needs (Any): 硬依赖服务集合。
            wants (Any): 软依赖服务集合。
        """
        who = str(owner or "").strip()
        if not who:
            return
        self._needs[who] = self._names(needs)
        self._wants[who] = self._names(wants)

    def inject(
        self,
        owner: str,
        needs: Any = None,
        wants: Any = None,
        ready: Optional[Callable[[], Any]] = None,
    ) -> None:
        """注册动态注入回调并在依赖满足时执行或排队等待。

        Args:
            owner (str): 实例 ID。
            needs (Any): 硬依赖服务集合。
            wants (Any): 软依赖服务集合。
            ready (Optional[Callable[[], Any]]): 依赖满足后的回调。
        """
        who = str(owner or "").strip()
        if not who:
            return

        needset = self._names(needs)
        wantset = self._names(wants)
        self.bind(who, needset, wantset)
        if ready is None:
            return

        waiter = _Waiter(owner=who, needs=needset, wants=wantset, ready=ready)
        if not self.miss(who):
            self._call(waiter.ready)
            return

        self._waiters.append(waiter)

    def miss(self, owner: str) -> set[str]:
        """返回指定实例当前缺失的硬依赖服务集合。

        Args:
            owner (str): 实例 ID。

        Returns:
            set[str]: 缺失的服务名集合。
        """
        who = str(owner or "").strip()
        if not who:
            return set()

        missing: set[str] = set()
        for name in self._needs.get(who, set()):
            if not self.ready(name):
                missing.add(name)
        return missing

    def get(self, name: str, default: Any = None) -> Any:
        """读取服务值并在多提供者场景下返回稳定选择结果。

        Args:
            name (str): 服务名。
            default (Any): 未命中时返回的默认值。

        Returns:
            Any: 命中的服务值或默认值。
        """
        service = str(name or "").strip()
        if not service:
            return default

        providers = self._values.get(service, {})
        if not providers:
            return default

        owner = sorted(providers.keys())[0]
        return providers.get(owner, default)

    def take(self, name: str, owner: Optional[str] = None, default: Any = None) -> Any:
        """优先按指定提供者读取服务值并在未命中时回退默认策略。

        Args:
            name (str): 服务名。
            owner (Optional[str]): 指定提供者实例 ID。
            default (Any): 未命中时返回的默认值。

        Returns:
            Any: 命中的服务值或默认值。
        """
        service = str(name or "").strip()
        who = str(owner or "").strip()
        if not service:
            return default

        providers = self._values.get(service, {})
        if who and who in providers:
            return providers.get(who, default)
        return self.get(service, default)

    def ready(self, name: str) -> bool:
        """判断指定服务是否已有至少一个可用值。

        Args:
            name (str): 服务名。

        Returns:
            bool: 有可用值返回 True，否则返回 False。
        """
        service = str(name or "").strip()
        return bool(self._values.get(service))

    def declared(self, name: str) -> bool:
        """判断指定服务名是否已经被声明过。

        Args:
            name (str): 服务名。

        Returns:
            bool: 已声明返回 True，否则返回 False。
        """
        service = str(name or "").strip()
        return service in self._declared

    def owners(self, name: str) -> set[str]:
        """返回声明可提供该服务的实例集合。

        Args:
            name (str): 服务名。

        Returns:
            set[str]: 提供者实例 ID 集合。
        """
        service = str(name or "").strip()
        return set(self._owners.get(service, set()))

    def users(self, name: str) -> set[str]:
        """返回在依赖声明中引用该服务的实例集合。

        Args:
            name (str): 服务名。

        Returns:
            set[str]: 使用者实例 ID 集合。
        """
        service = str(name or "").strip()
        if not service:
            return set()

        result: set[str] = set()
        for owner, needs in self._needs.items():
            if service in needs:
                result.add(owner)
        for owner, wants in self._wants.items():
            if service in wants:
                result.add(owner)
        return result

    def drop(self, owner: str) -> None:
        """移除实例的依赖记录与其提供的服务值并触发重算流程。

        Args:
            owner (str): 被移除的实例 ID。
        """
        who = str(owner or "").strip()
        if not who:
            return

        self._needs.pop(who, None)
        self._wants.pop(who, None)
        self._waiters = [item for item in self._waiters if item.owner != who]

        changed: list[tuple[str, set[str]]] = []
        for service, providers in list(self._values.items()):
            if who not in providers:
                continue
            users = self.users(service)
            changed.append((service, users))
            providers.pop(who, None)
            if not providers:
                self._values.pop(service, None)

        for service, users in changed:
            self._emit(self._before, service, users)
            self._emit(self._after, service, users)

        for service, owners in list(self._owners.items()):
            owners.discard(who)
            if not owners:
                self._owners.pop(service, None)

        self._flush()

    def clear(self) -> None:
        """清空注册中心的全部运行态数据。"""
        self._declared.clear()
        self._owners.clear()
        self._values.clear()
        self._needs.clear()
        self._wants.clear()
        self._waiters.clear()

    def _emit(self, listeners: list[Callable[[str, set[str]], Any]], name: str, users: set[str]) -> None:
        """将服务变化消息分发给给定监听器集合。

        Args:
            listeners (list[Callable[[str, set[str]], Any]]): 待执行的监听器列表。
            name (str): 变化服务名。
            users (set[str]): 受影响实例集合。
        """
        for listener in listeners:
            self._call(listener, name, set(users))

    def _flush(self) -> None:
        """重试等待队列中依赖已满足的动态注入回调。"""
        if not self._waiters:
            return

        pending = list(self._waiters)
        self._waiters.clear()
        for item in pending:
            if self.miss(item.owner):
                self._waiters.append(item)
                continue
            self._call(item.ready)

    @staticmethod
    def _call(func: Callable[..., Any], *args: Any) -> None:
        """安全执行回调并在需要时调度异步任务。

        Args:
            func (Callable[..., Any]): 目标回调。
            *args (Any): 传给回调的位置参数。
        """
        try:
            result = func(*args)
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    return
                asyncio.ensure_future(result)
        except Exception:
            return
