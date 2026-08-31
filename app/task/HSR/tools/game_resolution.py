"""临时把本地星穹铁道分辨率固定为 1920×1080，并可靠恢复注册表。"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any

try:
    import winreg as _winreg
except ImportError:  # pragma: no cover - HSR 本地游戏只支持 Windows
    _winreg = None


HSR_REGISTRY_PATHS = (
    r"Software\miHoYo\崩坏：星穹铁道",
    r"Software\Cognosphere\Star Rail",
    r"Software\miHoYo\Star Rail",
)

_WIDTH_VALUE = "Screenmanager Resolution Width_h182942802"
_HEIGHT_VALUE = "Screenmanager Resolution Height_h2627697771"
_USE_NATIVE_VALUE = "Screenmanager Resolution Use Native_h1405027254"
_PC_RESOLUTION_VALUE = "GraphicsSettings_PCResolution_h431323223"
_MANAGED_VALUES = (
    _WIDTH_VALUE,
    _HEIGHT_VALUE,
    _USE_NATIVE_VALUE,
    _PC_RESOLUTION_VALUE,
)

_ACTIVE_GUARD = threading.RLock()
_ACTIVE_OWNER: int | None = None


@dataclass(frozen=True, slots=True)
class _RegistryValueSnapshot:
    exists: bool
    value: Any = None
    value_type: int | None = None


class HSRGameResolutionOverride:
    """在 MAS 启动游戏前临时写入分辨率，结束时恢复全部原值和类型。"""

    def __init__(self, registry_module: Any | None = None) -> None:
        self._registry = registry_module if registry_module is not None else _winreg
        self._snapshots: dict[str, dict[str, _RegistryValueSnapshot]] = {}
        self._active = False
        self._owner = id(self)

    @property
    def active(self) -> bool:
        return self._active

    @property
    def target_count(self) -> int:
        return len(self._snapshots)

    def apply(self) -> bool:
        """只在首次启动前快照，并在重启前再次写入目标值。"""

        registry = self._require_registry()
        with _ACTIVE_GUARD:
            self._claim_owner()
            if self._active:
                self._write_targets(registry)
                return False

            try:
                paths = [path for path in HSR_REGISTRY_PATHS if self._key_exists(path)]
                if not paths:
                    raise RuntimeError(
                        "未找到星穹铁道当前用户注册表，无法临时设置分辨率"
                    )
                for path in paths:
                    self._snapshots[path] = self._snapshot_key(registry, path)
                self._write_targets(registry)
                self._active = True
            except Exception:
                self._restore_snapshots(registry, suppress_errors=True)
                self._snapshots.clear()
                self._release_owner()
                raise
        return True

    def restore(self) -> bool:
        """恢复所有原始值；原本不存在的值会被删除。"""

        registry = self._require_registry()
        with _ACTIVE_GUARD:
            if not self._snapshots:
                self._active = False
                self._release_owner()
                return False

            errors = self._restore_snapshots(registry, suppress_errors=False)
            if errors:
                raise RuntimeError("；".join(errors))
            self._snapshots.clear()
            self._active = False
            self._release_owner()
        return True

    def _require_registry(self) -> Any:
        if self._registry is None:
            raise RuntimeError("当前系统不支持 Windows 注册表，无法临时设置分辨率")
        return self._registry

    def _claim_owner(self) -> None:
        global _ACTIVE_OWNER
        if _ACTIVE_OWNER not in (None, self._owner):
            raise RuntimeError("已有其他 HSR 任务正在临时管理游戏分辨率")
        _ACTIVE_OWNER = self._owner

    def _release_owner(self) -> None:
        global _ACTIVE_OWNER
        if _ACTIVE_OWNER == self._owner:
            _ACTIVE_OWNER = None

    def _key_exists(self, path: str) -> bool:
        registry = self._require_registry()
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, path):
                return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _snapshot_key(registry: Any, path: str) -> dict[str, _RegistryValueSnapshot]:
        access = registry.KEY_QUERY_VALUE | registry.KEY_SET_VALUE
        snapshots: dict[str, _RegistryValueSnapshot] = {}
        with registry.OpenKey(registry.HKEY_CURRENT_USER, path, 0, access) as key:
            for name in _MANAGED_VALUES:
                try:
                    value, value_type = registry.QueryValueEx(key, name)
                    snapshots[name] = _RegistryValueSnapshot(
                        exists=True,
                        value=value,
                        value_type=value_type,
                    )
                except FileNotFoundError:
                    snapshots[name] = _RegistryValueSnapshot(exists=False)
        return snapshots

    def _write_targets(self, registry: Any) -> None:
        access = registry.KEY_QUERY_VALUE | registry.KEY_SET_VALUE
        for path, snapshots in self._snapshots.items():
            with registry.OpenKey(registry.HKEY_CURRENT_USER, path, 0, access) as key:
                registry.SetValueEx(key, _WIDTH_VALUE, 0, registry.REG_DWORD, 1920)
                registry.SetValueEx(key, _HEIGHT_VALUE, 0, registry.REG_DWORD, 1080)
                registry.SetValueEx(key, _USE_NATIVE_VALUE, 0, registry.REG_DWORD, 0)
                registry.SetValueEx(
                    key,
                    _PC_RESOLUTION_VALUE,
                    0,
                    registry.REG_BINARY,
                    self._pc_resolution_payload(snapshots),
                )

    @staticmethod
    def _pc_resolution_payload(snapshots: dict[str, _RegistryValueSnapshot]) -> bytes:
        payload: dict[str, Any] = {}
        original = snapshots.get(_PC_RESOLUTION_VALUE)
        if original is not None and isinstance(original.value, bytes):
            try:
                decoded = original.value.rstrip(b"\x00").decode("utf-8")
                loaded = json.loads(decoded)
                if isinstance(loaded, dict):
                    payload.update(loaded)
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

        payload["width"] = 1920
        payload["height"] = 1080
        payload["isFullScreen"] = False
        return (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\x00"
        )

    def _restore_snapshots(
        self,
        registry: Any,
        *,
        suppress_errors: bool,
    ) -> list[str]:
        access = registry.KEY_QUERY_VALUE | registry.KEY_SET_VALUE
        errors: list[str] = []
        for path, snapshots in reversed(tuple(self._snapshots.items())):
            try:
                with registry.OpenKey(
                    registry.HKEY_CURRENT_USER,
                    path,
                    0,
                    access,
                ) as key:
                    for name, snapshot in snapshots.items():
                        try:
                            if snapshot.exists:
                                assert snapshot.value_type is not None
                                registry.SetValueEx(
                                    key,
                                    name,
                                    0,
                                    snapshot.value_type,
                                    snapshot.value,
                                )
                            else:
                                try:
                                    registry.DeleteValue(key, name)
                                except FileNotFoundError:
                                    pass
                        except Exception as exc:  # noqa: BLE001
                            errors.append(f"恢复注册表值 {name} 失败：{exc}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"打开星铁注册表 {path} 失败：{exc}")

        if errors and not suppress_errors:
            return errors
        return []


__all__ = ["HSRGameResolutionOverride", "HSR_REGISTRY_PATHS"]
