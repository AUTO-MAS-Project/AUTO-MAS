"""按 exe 路径反查 Unity 游戏的注册表，临时改成指定尺寸的窗口分辨率并可靠恢复。

Unity 播放器把 PlayerPrefs 存在 ``HKCU\\Software\\<公司名>\\<产品名>``，两个名字就写在
``<exe 同名>_Data\\app.info`` 的前两行——所以只要用户选了游戏本体的 exe，就能反查到
它的注册表键，不需要为每个游戏单独维护路径表。分辨率相关的几个 ``Screenmanager *``
值是 Unity 播放器自己的，名字（含 ``_h<hash>`` 后缀）在所有 Unity 游戏里都一样，
本机实测 原神 / 星穹铁道 / 终末地 三个游戏的键名完全一致。

已知边界：

- 只对 Unity 引擎的游戏有效。没有 ``app.info`` 的 exe（UE 等引擎、或选的是启动器）
  直接返回 None，由调用方决定是否提示。
- 部分游戏在 Unity 的这几个值之外还有一层自己的图形设置（星穹铁道的
  ``GraphicsSettings_PCResolution``、终末地的 ``video_resolution_*``），启动后可能
  按自己那层重新套一遍分辨率。这里**只改 Unity 那层**，游戏自有层的键名与语义各不
  相同，未经实机验证不写；HSR 专项的 ``HSRGameResolutionOverride`` 是那种做法的例子。
- 游戏正常退出时 Unity 会把当时的分辨率写回这些值，所以恢复不能只删自己写的那几个，
  必须按快照把原值与原类型整表写回、原本不存在的删掉。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import winreg as _winreg
except ImportError:  # pragma: no cover - PC 端游戏只在 Windows 上跑
    _winreg = None


UNITY_APP_INFO_NAME = "app.info"

# Unity 播放器的分辨率键。后缀是键名的哈希，跨游戏、跨 Unity 版本稳定。
_WIDTH_VALUE = "Screenmanager Resolution Width_h182942802"
_HEIGHT_VALUE = "Screenmanager Resolution Height_h2627697771"
_USE_NATIVE_VALUE = "Screenmanager Resolution Use Native_h1405027254"
# Unity 2018.1+ 的 FullScreenMode 枚举：0 独占全屏 / 1 全屏窗口 / 2 最大化窗口 / 3 窗口
_FULLSCREEN_MODE_VALUE = "Screenmanager Fullscreen mode_h3630240806"
# 更老的 Unity 只有布尔全屏开关（原神仍是这一代）
_LEGACY_IS_FULLSCREEN_VALUE = "Screenmanager Is Fullscreen mode_h3981298716"
# 新版 Unity 在全屏时另存一份窗口模式下的尺寸，切回窗口时按它恢复
_WINDOW_WIDTH_VALUE = "Screenmanager Resolution Window Width_h2524650974"
_WINDOW_HEIGHT_VALUE = "Screenmanager Resolution Window Height_h1684712807"

_FULLSCREEN_MODE_WINDOWED = 3

# 受管键：写入时全部 REG_DWORD，恢复时按快照回写、原本不存在的删掉，多写无害。
MANAGED_VALUES: tuple[str, ...] = (
    _WIDTH_VALUE,
    _HEIGHT_VALUE,
    _WINDOW_WIDTH_VALUE,
    _WINDOW_HEIGHT_VALUE,
    _USE_NATIVE_VALUE,
    _FULLSCREEN_MODE_VALUE,
    _LEGACY_IS_FULLSCREEN_VALUE,
)

#: 脚本配置 ``Game.UnityResolution`` 的可选值 → (宽, 高)。``Off`` 不在表里，表示不改。
RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "1920x1080": (1920, 1080),
    "1280x720": (1280, 720),
}


def parse_resolution_option(value: object) -> tuple[int, int] | None:
    """把 ``Game.UnityResolution`` 的配置值解析成 (宽, 高)；``Off`` / 空 / 未知返回 None。"""

    return RESOLUTION_PRESETS.get(str(value or "").strip())


def read_unity_resolution(
    exe_path: Path,
    registry_module: Any | None = None,
) -> tuple[int, int] | None:
    """读取 Unity 播放器当前保存的分辨率。

    路径和键名沿用 :class:`UnityGameResolutionOverride` 的注册表实现；这里只做只读
    查询，不申请写权限，也不会创建或修改任何键。无法反查 Unity 路径、运行在非
    Windows 系统、注册表键/值不存在或值不是正整数时返回 ``None``。
    """

    registry_path = resolve_unity_registry_path(exe_path)
    registry = registry_module if registry_module is not None else _winreg
    if registry_path is None or registry is None:
        return None

    try:
        with registry.OpenKey(
            registry.HKEY_CURRENT_USER,
            registry_path,
            0,
            registry.KEY_QUERY_VALUE,
        ) as key:
            width, _ = registry.QueryValueEx(key, _WIDTH_VALUE)
            height, _ = registry.QueryValueEx(key, _HEIGHT_VALUE)
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None

    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def read_unity_display_type(
    exe_path: Path,
    registry_module: Any | None = None,
    *,
    preferred_value_name: str | None = None,
) -> str | None:
    """读取游戏保存的显示模式；可优先读取调用方提供的布尔全屏值。"""

    registry_path = resolve_unity_registry_path(exe_path)
    registry = registry_module if registry_module is not None else _winreg
    if registry_path is None or registry is None:
        return None

    try:
        with registry.OpenKey(
            registry.HKEY_CURRENT_USER,
            registry_path,
            0,
            registry.KEY_QUERY_VALUE,
        ) as key:
            candidates = (
                ((preferred_value_name, {0, 1}),) if preferred_value_name else ()
            ) + (
                (_FULLSCREEN_MODE_VALUE, {0, 1, 2, 3}),
                (_LEGACY_IS_FULLSCREEN_VALUE, {0, 1}),
            )
            for name, valid_values in candidates:
                try:
                    value, _ = registry.QueryValueEx(key, name)
                    mode = int(value)
                except (FileNotFoundError, OSError, TypeError, ValueError):
                    continue
                if mode in valid_values:
                    if name == _FULLSCREEN_MODE_VALUE:
                        return "Window" if mode == _FULLSCREEN_MODE_WINDOWED else "Fullscreen"
                    return "Fullscreen" if mode == 1 else "Window"
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None
    return None


def _target_values(width: int, height: int) -> tuple[tuple[str, int], ...]:
    return (
        (_WIDTH_VALUE, width),
        (_HEIGHT_VALUE, height),
        (_WINDOW_WIDTH_VALUE, width),
        (_WINDOW_HEIGHT_VALUE, height),
        (_USE_NATIVE_VALUE, 0),
        (_FULLSCREEN_MODE_VALUE, _FULLSCREEN_MODE_WINDOWED),
        (_LEGACY_IS_FULLSCREEN_VALUE, 0),
    )


# 同一个注册表键同时只能有一个覆盖者，否则后者的快照会把前者写入的目标值当原值恢复。
# 按键路径而不是全局互斥：不同 MFW 脚本可能同时跑不同的游戏。
_ACTIVE_GUARD = threading.RLock()
_ACTIVE_OWNERS: dict[str, int] = {}


@dataclass(frozen=True, slots=True)
class _RegistryValueSnapshot:
    exists: bool
    value: Any = None
    value_type: int | None = None


def resolve_unity_registry_path(exe_path: Path) -> str | None:
    """从游戏 exe 反查 Unity PlayerPrefs 所在的 HKCU 相对路径。

    读 ``<exe 同名>_Data\\app.info``：第一行公司名、第二行产品名。文件不存在或
    内容不完整都视为「不是 Unity 游戏」返回 None，不抛错。
    """

    exe_path = Path(exe_path)
    info_path = exe_path.parent / f"{exe_path.stem}_Data" / UNITY_APP_INFO_NAME
    try:
        raw = info_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    lines = [line.strip() for line in raw.splitlines()]
    if len(lines) < 2 or not lines[0] or not lines[1]:
        return None
    company, product = lines[0], lines[1]
    if "\\" in company or "\\" in product:
        # 名字里带反斜杠会拆成多级键，Unity 自己也不支持，视为不可反查
        return None
    return rf"Software\{company}\{product}"


class UnityGameResolutionOverride:
    """在 MAS 启动游戏前临时写入指定尺寸的窗口模式，游戏关闭后恢复全部原值和类型。"""

    def __init__(
        self,
        registry_path: str,
        width: int,
        height: int,
        registry_module: Any | None = None,
    ) -> None:
        self.registry_path = registry_path
        self.width = int(width)
        self.height = int(height)
        self._registry = registry_module if registry_module is not None else _winreg
        self._snapshot: dict[str, _RegistryValueSnapshot] = {}
        self._active = False
        self._owner = id(self)

    @classmethod
    def for_executable(
        cls,
        exe_path: Path,
        width: int,
        height: int,
        registry_module: Any | None = None,
    ) -> UnityGameResolutionOverride | None:
        """按 exe 反查注册表路径；不是 Unity 游戏返回 None。"""

        registry_path = resolve_unity_registry_path(exe_path)
        if registry_path is None:
            return None
        return cls(registry_path, width, height, registry_module=registry_module)

    @property
    def label(self) -> str:
        return f"{self.width}×{self.height}"

    def apply(self) -> bool:
        """首次调用先快照再写目标值，返回 True；已生效时只重写目标值，返回 False。"""

        registry = self._require_registry()
        with _ACTIVE_GUARD:
            self._claim_owner()
            if self._active:
                self._write_targets(registry)
                return False

            try:
                if not self._key_exists(registry):
                    raise RuntimeError(
                        f"未找到注册表键 HKCU\\{self.registry_path}，"
                        "游戏可能尚未首次运行过"
                    )
                self._snapshot = self._snapshot_key(registry)
                self._write_targets(registry)
                self._active = True
            except Exception:
                if self._snapshot:
                    self._restore_snapshot(registry, suppress_errors=True)
                self._snapshot = {}
                self._release_owner()
                raise
        return True

    def restore(self) -> bool:
        """恢复所有原始值；原本不存在的值会被删除。未生效时返回 False。"""

        registry = self._require_registry()
        with _ACTIVE_GUARD:
            if not self._snapshot:
                self._active = False
                self._release_owner()
                return False

            errors = self._restore_snapshot(registry, suppress_errors=False)
            if errors:
                raise RuntimeError("；".join(errors))
            self._snapshot = {}
            self._active = False
            self._release_owner()
        return True

    def _require_registry(self) -> Any:
        if self._registry is None:
            raise RuntimeError("当前系统不支持 Windows 注册表，无法临时设置分辨率")
        return self._registry

    def _claim_owner(self) -> None:
        owner = _ACTIVE_OWNERS.get(self.registry_path)
        if owner not in (None, self._owner):
            raise RuntimeError(
                f"已有其他任务正在临时管理 HKCU\\{self.registry_path} 的分辨率"
            )
        _ACTIVE_OWNERS[self.registry_path] = self._owner

    def _release_owner(self) -> None:
        if _ACTIVE_OWNERS.get(self.registry_path) == self._owner:
            _ACTIVE_OWNERS.pop(self.registry_path, None)

    def _key_exists(self, registry: Any) -> bool:
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, self.registry_path):
                return True
        except FileNotFoundError:
            return False

    def _open_key(self, registry: Any) -> Any:
        access = registry.KEY_QUERY_VALUE | registry.KEY_SET_VALUE
        return registry.OpenKey(
            registry.HKEY_CURRENT_USER, self.registry_path, 0, access
        )

    def _snapshot_key(self, registry: Any) -> dict[str, _RegistryValueSnapshot]:
        snapshot: dict[str, _RegistryValueSnapshot] = {}
        with self._open_key(registry) as key:
            for name in MANAGED_VALUES:
                try:
                    value, value_type = registry.QueryValueEx(key, name)
                    snapshot[name] = _RegistryValueSnapshot(
                        exists=True, value=value, value_type=value_type
                    )
                except FileNotFoundError:
                    snapshot[name] = _RegistryValueSnapshot(exists=False)
        return snapshot

    def _write_targets(self, registry: Any) -> None:
        with self._open_key(registry) as key:
            for name, value in _target_values(self.width, self.height):
                registry.SetValueEx(key, name, 0, registry.REG_DWORD, value)

    def _restore_snapshot(self, registry: Any, *, suppress_errors: bool) -> list[str]:
        errors: list[str] = []
        try:
            with self._open_key(registry) as key:
                for name, snapshot in self._snapshot.items():
                    try:
                        if snapshot.exists:
                            assert snapshot.value_type is not None
                            registry.SetValueEx(
                                key, name, 0, snapshot.value_type, snapshot.value
                            )
                        else:
                            try:
                                registry.DeleteValue(key, name)
                            except FileNotFoundError:
                                pass
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"恢复注册表值 {name} 失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"打开注册表 HKCU\\{self.registry_path} 失败：{exc}")

        if errors and not suppress_errors:
            return errors
        return []


__all__ = [
    "MANAGED_VALUES",
    "RESOLUTION_PRESETS",
    "UnityGameResolutionOverride",
    "parse_resolution_option",
    "read_unity_resolution",
    "resolve_unity_registry_path",
]
