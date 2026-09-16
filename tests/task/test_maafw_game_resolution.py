"""MaaFW 内置运行：按 exe 反查 Unity 注册表并临时固定 1920×1080。"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.task.MaaFW.tools.embedded import game_resolution
from app.task.MaaFW.tools.embedded.game_resolution import (
    MANAGED_VALUES,
    UnityGameResolutionOverride,
    resolve_unity_registry_path,
)


class _FakeKey:
    def __init__(self, store: dict[str, tuple[object, int]]) -> None:
        self.store = store

    def __enter__(self) -> "_FakeKey":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class FakeWinreg:
    """只模拟 game_resolution 用到的那几个 winreg 调用。

    值的形状照抄真实注册表：``(value, type)``，DWORD 用 REG_DWORD=4、二进制用 REG_BINARY=3。
    """

    HKEY_CURRENT_USER = object()
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2
    REG_DWORD = 4
    REG_BINARY = 3

    def __init__(self, keys: dict[str, dict[str, tuple[object, int]]]) -> None:
        self.keys = keys

    def OpenKey(self, hive: object, path: str, reserved: int = 0, access: int = 0):
        if path not in self.keys:
            raise FileNotFoundError(path)
        return _FakeKey(self.keys[path])

    @staticmethod
    def QueryValueEx(key: _FakeKey, name: str) -> tuple[object, int]:
        if name not in key.store:
            raise FileNotFoundError(name)
        return key.store[name]

    @staticmethod
    def SetValueEx(
        key: _FakeKey, name: str, reserved: int, value_type: int, value: object
    ) -> None:
        key.store[name] = (value, value_type)

    @staticmethod
    def DeleteValue(key: _FakeKey, name: str) -> None:
        if name not in key.store:
            raise FileNotFoundError(name)
        del key.store[name]


# 照抄本机 HKCU\Software\Hypergryph\Endfield 里与分辨率有关的那几项（1280×720 窗口）
ENDFIELD_PATH = r"Software\Hypergryph\Endfield"
ENDFIELD_VALUES: dict[str, tuple[object, int]] = {
    "Screenmanager Resolution Width_h182942802": (1280, 4),
    "Screenmanager Resolution Height_h2627697771": (720, 4),
    "Screenmanager Resolution Use Native_h1405027254": (0, 4),
    "Screenmanager Fullscreen mode_h3630240806": (3, 4),
    "Screenmanager Resolution Window Width_h2524650974": (1280, 4),
    "Screenmanager Resolution Window Height_h1684712807": (720, 4),
    # 游戏自有的一层，不在管理范围内，必须原样留着
    "video_resolution_width_h583690364": (1280, 4),
    "video_full_screen_h1998742411": (0, 4),
}


class ResolveUnityRegistryPathTest(unittest.TestCase):
    def test_reads_company_and_product_from_app_info(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Endfield_Data").mkdir()
            (root / "Endfield_Data" / "app.info").write_text(
                "Hypergryph\nEndfield\n", encoding="utf-8"
            )
            exe = root / "Endfield.exe"
            exe.write_bytes(b"")
            self.assertEqual(
                resolve_unity_registry_path(exe), r"Software\Hypergryph\Endfield"
            )

    def test_keeps_non_ascii_names_and_strips_bom(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "StarRail_Data").mkdir()
            (root / "StarRail_Data" / "app.info").write_text(
                "miHoYo\n崩坏：星穹铁道", encoding="utf-8-sig"
            )
            self.assertEqual(
                resolve_unity_registry_path(root / "StarRail.exe"),
                r"Software\miHoYo\崩坏：星穹铁道",
            )

    def test_returns_none_when_not_a_unity_game(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "Client-Win64-Shipping.exe"
            exe.write_bytes(b"")
            self.assertIsNone(resolve_unity_registry_path(exe))

    def test_returns_none_when_app_info_incomplete(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Game_Data").mkdir()
            (root / "Game_Data" / "app.info").write_text(
                "OnlyCompany\n", encoding="utf-8"
            )
            self.assertIsNone(resolve_unity_registry_path(root / "Game.exe"))


class UnityGameResolutionOverrideTest(unittest.TestCase):
    def setUp(self) -> None:
        game_resolution._ACTIVE_OWNERS.clear()
        self.registry = FakeWinreg({ENDFIELD_PATH: dict(ENDFIELD_VALUES)})
        self.store = self.registry.keys[ENDFIELD_PATH]

    def test_apply_writes_1080p_windowed_and_restore_puts_everything_back(self) -> None:
        override = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )

        self.assertTrue(override.apply())

        self.assertEqual(
            self.store["Screenmanager Resolution Width_h182942802"], (1920, 4)
        )
        self.assertEqual(
            self.store["Screenmanager Resolution Height_h2627697771"], (1080, 4)
        )
        self.assertEqual(
            self.store["Screenmanager Resolution Window Width_h2524650974"], (1920, 4)
        )
        self.assertEqual(
            self.store["Screenmanager Fullscreen mode_h3630240806"], (3, 4)
        )
        self.assertEqual(
            self.store["Screenmanager Resolution Use Native_h1405027254"], (0, 4)
        )
        # 老 Unity 的布尔全屏键原本不存在，也会被写成 0
        self.assertEqual(
            self.store["Screenmanager Is Fullscreen mode_h3981298716"], (0, 4)
        )
        # 游戏自有层不碰
        self.assertEqual(self.store["video_resolution_width_h583690364"], (1280, 4))

        # 模拟游戏退出时 Unity 把当时的分辨率写回：恢复必须按快照整表回写
        self.store["Screenmanager Resolution Width_h182942802"] = (1920, 4)
        self.assertTrue(override.restore())
        self.assertEqual(self.store, ENDFIELD_VALUES)
        self.assertEqual(game_resolution._ACTIVE_OWNERS, {})

    def test_reapply_keeps_original_snapshot(self) -> None:
        override = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )
        self.assertTrue(override.apply())
        # 游戏重启前再次 apply：不重新快照，否则会把 1920×1080 当成原值
        self.assertFalse(override.apply())
        self.assertTrue(override.restore())
        self.assertEqual(self.store, ENDFIELD_VALUES)

    def test_restore_without_apply_is_noop(self) -> None:
        override = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )
        self.assertFalse(override.restore())
        self.assertEqual(self.store, ENDFIELD_VALUES)

    def test_apply_fails_when_key_missing_and_leaves_nothing_behind(self) -> None:
        override = UnityGameResolutionOverride(
            r"Software\Nobody\NeverRan", registry_module=self.registry
        )
        with self.assertRaises(RuntimeError):
            override.apply()
        self.assertEqual(game_resolution._ACTIVE_OWNERS, {})
        self.assertFalse(override.restore())

    def test_same_key_cannot_be_owned_twice_but_other_keys_can(self) -> None:
        other_path = r"Software\miHoYo\崩坏：星穹铁道"
        self.registry.keys[other_path] = {
            "Screenmanager Resolution Width_h182942802": (2560, 4),
            "Screenmanager Resolution Height_h2627697771": (1440, 4),
        }
        first = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )
        second = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )
        other = UnityGameResolutionOverride(other_path, registry_module=self.registry)

        self.assertTrue(first.apply())
        with self.assertRaises(RuntimeError):
            second.apply()
        self.assertTrue(other.apply())

        self.assertTrue(first.restore())
        self.assertTrue(other.restore())
        self.assertEqual(self.store, ENDFIELD_VALUES)
        self.assertEqual(
            self.registry.keys[other_path],
            {
                "Screenmanager Resolution Width_h182942802": (2560, 4),
                "Screenmanager Resolution Height_h2627697771": (1440, 4),
            },
        )

    def test_managed_values_cover_every_written_name(self) -> None:
        override = UnityGameResolutionOverride(
            ENDFIELD_PATH, registry_module=self.registry
        )
        override.apply()
        written = set(self.store) - set(ENDFIELD_VALUES)
        self.assertTrue(written.issubset(MANAGED_VALUES))


if __name__ == "__main__":
    unittest.main()
