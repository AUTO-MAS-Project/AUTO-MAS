"""只发现随应用交付的内置清单，再由宿主显式加载注册入口。"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.core.notify.channels.registry import ChannelRegistry, validate_channel
from app.models.notification.channel import CHANNEL_INTERFACE_VERSION, NotifyChannel

BUILTIN_CHANNEL_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ChannelManifest:
    id: str
    entrypoint: str
    requires: tuple[str, ...]


@dataclass(frozen=True)
class ChannelDiagnostic:
    channel: str
    stage: str
    reason: str


def discover_channels(
    root: Path = BUILTIN_CHANNEL_ROOT,
) -> tuple[tuple[ChannelManifest, ...], tuple[ChannelDiagnostic, ...]]:
    """仅读取指定内置目录的 JSON，不导入 Python 或创建任何传输资源。"""

    manifests: list[ChannelManifest] = []
    diagnostics: list[ChannelDiagnostic] = []
    for folder in sorted(root.iterdir(), key=lambda path: path.name):
        path = folder / "manifest.json"
        if folder.is_symlink() or not folder.is_dir() or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("清单必须为对象")
            if (
                type(data.get("interface_version")) is not int
                or data["interface_version"] != CHANNEL_INTERFACE_VERSION
            ):
                raise ValueError("不支持的接口版本")
            key = data.get("id")
            if (
                not isinstance(key, str)
                or re.fullmatch(r"[a-z][a-z0-9_]*", key) is None
            ):
                raise ValueError("渠道 ID 格式无效")
            if key != folder.name:
                raise ValueError("渠道 ID 与包目录不一致")
            entrypoint = data.get("entrypoint")
            if entrypoint != f"app.core.notify.channels.{key}:register":
                raise ValueError("注册入口必须位于该内置渠道包")
            if not (folder / "__init__.py").is_file():
                raise ValueError("注册入口包不存在")
            requires = data.get("requires")
            if not isinstance(requires, list) or any(
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                for name in requires
            ):
                raise ValueError("依赖声明必须为顶层模块名列表")
            manifests.append(ChannelManifest(key, entrypoint, tuple(requires)))
        except (ValueError, OSError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            if isinstance(exc, json.JSONDecodeError):
                reason = "JSON 格式错误"
            diagnostics.append(ChannelDiagnostic(folder.name, "manifest", reason))
    return tuple(manifests), tuple(diagnostics)


def register_channels(
    manifests: tuple[ChannelManifest, ...],
    *,
    discovery_errors: tuple[ChannelDiagnostic, ...] = (),
) -> tuple[ChannelRegistry, tuple[ChannelDiagnostic, ...]]:
    """完整声明校验成功后一次登记；重复 ID 全部隔离，不静默覆盖。"""

    entries: list[NotifyChannel] = []
    unavailable: set[str] = set()
    diagnostics = list(discovery_errors)
    counts = Counter(manifest.id for manifest in manifests)
    for manifest in manifests:
        if counts[manifest.id] > 1:
            diagnostics.append(
                ChannelDiagnostic(manifest.id, "register", "渠道 ID 重复")
            )
            continue
        try:
            missing = [
                name
                for name in manifest.requires
                if importlib.util.find_spec(name) is None
            ]
            if missing:
                diagnostics.append(
                    ChannelDiagnostic(manifest.id, "dependency", ", ".join(missing))
                )
                unavailable.add(manifest.id)
            module_name, name = manifest.entrypoint.split(":")
            # 防止程序内传入的清单绕过发现阶段的入口约束。
            if (
                module_name != f"app.core.notify.channels.{manifest.id}"
                or name != "register"
            ):
                raise ValueError("注册入口不在内置包内")
            registration = getattr(importlib.import_module(module_name), name)
            if not callable(registration):
                raise ValueError("注册入口不可调用")
            entry = registration()
            validate_channel(entry)
            if entry.key != manifest.id:
                raise ValueError("声明 ID 与清单不一致")
            entries.append(entry)
        except Exception as exc:
            # 模块异常可含敏感配置，诊断仅记录阶段、渠道和异常类型。
            diagnostics.append(
                ChannelDiagnostic(manifest.id, "register", type(exc).__name__)
            )
    # 声明保持可见以按既有启用配置构造目标；缺依赖时禁止绑定发送器。
    # 否则已有启用渠道会静默消失，被业务收尾误判为全部送达。
    registered = {entry.key for entry in entries}
    unresolved = {
        error.channel for error in diagnostics if error.channel not in registered
    }
    return (
        ChannelRegistry(entries, unavailable=unavailable, unresolved=unresolved),
        tuple(diagnostics),
    )
