"""验证通用脚本根目录联动与导入期信号冲突（v2）。

模拟 RootPath 联动：保存绝对路径，RootPath 变更时同步 Script 下各路径。
覆盖 open_file 导入与运行时改根目录两类场景。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import ClassVar

from blinker import Signal
from pydantic import Field

from app.config import (
    ConfigEntry,
    ConfigGroup,
    FieldChangeEvent,
    write_wire_toml,
)


def _fail(message: str) -> None:
    raise AssertionError(message)


def _ok(message: str) -> None:
    print(f"OK: {message}")


def _norm(path: str) -> str:
    return str(Path(path).resolve())


class GeneralScriptConfig(ConfigEntry):
    """精简版通用脚本配置，用于验证 RootPath 联动。"""

    class Info(ConfigGroup):
        name: str = "新通用脚本"
        root_path: str = str(Path.cwd())

    class Script(ConfigGroup):
        script_path: str = str(Path.cwd())
        config_path: str = str(Path.cwd())
        log_path: str = str(Path.cwd())

    info: Info = Field(default_factory=Info)
    script: Script = Field(default_factory=Script)

    _path_relatives: ClassVar[dict[str, str]] = {
        "script_path": "",
        "config_path": "",
        "log_path": "",
    }
    _sync_enabled: ClassVar[bool] = False
    # 钉住 RootPath 联动接收者，避免仅被 blinker weakref 持有而遭 GC
    _root_path_sync_receiver: ClassVar[object | None] = None

    @classmethod
    def _is_under_root(cls, root: str, target: str) -> bool:
        if not root or not target:
            return False
        try:
            Path(target).resolve().relative_to(Path(root).resolve())
            return True
        except ValueError:
            return False

    @classmethod
    def _capture_relatives(cls, entry: "GeneralScriptConfig") -> None:
        root = entry.info.root_path
        for name in cls._path_relatives:
            target = getattr(entry.script, name)
            if cls._is_under_root(root, target):
                rel = Path(target).resolve().relative_to(Path(root).resolve())
                cls._path_relatives[name] = rel.as_posix()
            else:
                cls._path_relatives[name] = ""

    @classmethod
    def _sync_paths_from_root(cls, entry: "GeneralScriptConfig", new_root: str) -> None:
        if not new_root:
            return
        root = Path(new_root).resolve()
        for name, relative in cls._path_relatives.items():
            if not relative or relative.startswith(".."):
                continue
            setattr(entry.script, name, str((root / relative).resolve()))

    @classmethod
    def install_root_path_sync(cls) -> None:
        async def _on_root_path(sender: object, event: FieldChangeEvent) -> None:
            entry = event.config
            if not isinstance(entry, cls):
                return
            if not cls._sync_enabled:
                return
            if event.old_value == event.value:
                return
            cls._sync_paths_from_root(entry, str(event.value))
            if entry._staged_ops:
                await entry.commit()

        # 钉住接收者，避免仅被 blinker weakref 持有而遭 GC
        cls._root_path_sync_receiver = _on_root_path
        cls.connect(_on_root_path, phase="runtime", group="info", field="root_path")


def _reset() -> None:
    GeneralScriptConfig.signal = Signal()
    GeneralScriptConfig._sync_enabled = False
    GeneralScriptConfig._root_path_sync_receiver = None


async def test_path_load_preserves_stored_paths() -> None:
    """load 后路径应与 TOML 一致，不被根目录联动改写。"""
    _reset()
    GeneralScriptConfig.install_root_path_sync()
    GeneralScriptConfig._sync_enabled = True

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "GameRoot"
        root.mkdir()
        stored = {
            "info": {"name": "测试脚本", "root_path": _norm(str(root))},
            "script": {
                "script_path": _norm(str(root / "bin" / "app.exe")),
                "config_path": _norm(str(root / "cfg" / "settings.ini")),
                "log_path": _norm(str(root / "logs" / "out.log")),
            },
        }
        path = Path(tmp) / "general.toml"
        write_wire_toml(path, stored)

        cfg = GeneralScriptConfig.build(file=path)
        await cfg.activate()

        if cfg.info.root_path != stored["info"]["root_path"]:
            _fail(f"RootPath 不一致: {cfg.info.root_path!r}")
        for key in ("script_path", "config_path", "log_path"):
            if getattr(cfg.script, key) != stored["script"][key]:
                _fail(f"导入后 {key} 被改写")
    _ok("path load 保留 TOML 内路径（init 不触发 runtime 联动）")


async def test_runtime_root_path_change_syncs_subpaths() -> None:
    """加载完成后修改 RootPath，应联动更新根内子路径。"""
    _reset()
    GeneralScriptConfig.install_root_path_sync()

    with tempfile.TemporaryDirectory() as tmp:
        old_root = Path(tmp) / "OldRoot"
        new_root = Path(tmp) / "NewRoot"
        old_root.mkdir()
        new_root.mkdir()

        cfg = GeneralScriptConfig.build(
            wire={
                "info": {"name": "联动测试", "root_path": _norm(str(old_root))},
                "script": {
                    "script_path": _norm(str(old_root / "bin" / "app.exe")),
                    "config_path": _norm(str(old_root / "cfg" / "settings.ini")),
                    "log_path": _norm(str(old_root / "logs" / "out.log")),
                },
            }
        )
        await cfg.activate()
        GeneralScriptConfig._capture_relatives(cfg)
        GeneralScriptConfig._sync_enabled = True

        cfg.info.root_path = _norm(str(new_root))
        await cfg.commit()

        expected_script = _norm(str(new_root / "bin" / "app.exe"))
        expected_config = _norm(str(new_root / "cfg" / "settings.ini"))
        if cfg.script.script_path != expected_script:
            _fail(f"运行时联动 script_path 失败: {cfg.script.script_path!r}")
        if cfg.script.config_path != expected_config:
            _fail(f"运行时联动 config_path 失败: {cfg.script.config_path!r}")
    _ok("运行时 RootPath 变更联动子路径")


async def test_import_deferred_sync_safe() -> None:
    """推荐模式：导入完成后 capture 相对路径，再启用联动。"""
    _reset()
    GeneralScriptConfig.install_root_path_sync()
    GeneralScriptConfig._sync_enabled = False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "GameRoot"
        root.mkdir()
        expected_script = _norm(str(root / "bin" / "app.exe"))

        path = Path(tmp) / "general.toml"
        write_wire_toml(
            path,
            {
                "info": {"root_path": _norm(str(root))},
                "script": {"script_path": expected_script},
            },
        )

        cfg = GeneralScriptConfig.build(file=path)
        await cfg.activate()

        GeneralScriptConfig._capture_relatives(cfg)
        GeneralScriptConfig._sync_enabled = True

        new_root = Path(tmp) / "MovedRoot"
        new_root.mkdir()
        cfg.info.root_path = _norm(str(new_root))
        await cfg.commit()

        if cfg.script.script_path != _norm(str(new_root / "bin" / "app.exe")):
            _fail("延迟启用联动后运行时同步失败")
        if cfg.script.script_path == expected_script:
            _fail("延迟启用联动仍保留旧绝对路径")
    _ok("导入后 capture + 启用联动模式安全")


async def main() -> int:
    tests = [
        test_path_load_preserves_stored_paths,
        test_runtime_root_path_change_syncs_subpaths,
        test_import_deferred_sync_safe,
    ]
    failed = 0
    for test in tests:
        try:
            await test()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL: {test.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
