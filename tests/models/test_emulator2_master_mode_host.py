import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.utils.emulator2 import master_mode
from app.utils.emulator2.master_mode import (
    LDPLAYER_MARKER_KEY,
    apply_host_mode,
    apply_ldplayer_data_ini,
    apply_splash_placeholders,
    ldplayer_data_ini_path,
)


class DataIniTest(unittest.TestCase):
    """雷电渠道配置 ``data\\data.ini`` 的写入与还原，按 ``GetPrivateProfileString`` 的口径。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data.ini"

    def write(self, raw: bytes) -> None:
        self.path.write_bytes(raw)

    def read(self) -> str:
        return self.path.read_bytes().decode("latin-1")

    def test_path_is_under_data_dir(self) -> None:
        self.assertEqual(
            ldplayer_data_ini_path(Path(r"D:\leidian\LDPlayer14")),
            Path(r"D:\leidian\LDPlayer14\data\data.ini"),
        )

    def test_enable_appends_keys_and_marker_to_bare_section(self) -> None:
        """雷电 14 装完就是一行 ``[setting]``，没有换行符。"""
        self.write(b"[setting]")

        self.assertTrue(apply_ldplayer_data_ini(self.path, True))
        self.assertEqual(
            self.read(),
            "[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:-,launchadshow:-\r\n",
        )

    def test_enable_is_idempotent(self) -> None:
        self.write(b"[setting]")
        apply_ldplayer_data_ini(self.path, True)
        before = self.read()

        self.assertFalse(apply_ldplayer_data_ini(self.path, True))
        self.assertEqual(self.read(), before)

    def test_disable_restores_original_file(self) -> None:
        self.write(b"[setting]\r\ntitle=x\r\n")
        apply_ldplayer_data_ini(self.path, True)

        self.assertTrue(apply_ldplayer_data_ini(self.path, False))
        self.assertEqual(self.read(), "[setting]\r\ntitle=x\r\n")

    def test_disable_without_marker_leaves_file_untouched(self) -> None:
        """从没开过模式的机器上，关着的模式不能去动渠道包自带的值。"""
        self.write(b"[setting]\r\nadshow=0\r\n")

        self.assertFalse(apply_ldplayer_data_ini(self.path, False))
        self.assertEqual(self.read(), "[setting]\r\nadshow=0\r\n")

    def test_enable_keeps_channel_zero_and_only_records_added_keys(self) -> None:
        """渠道包自带 ``adshow=0`` 时只补 ``launchadshow``，还原时 ``adshow`` 原样留着。"""
        self.write(b"[setting]\r\nadshow=0\r\n")

        apply_ldplayer_data_ini(self.path, True)
        self.assertEqual(
            self.read(),
            "[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:0,launchadshow:-\r\n",
        )

        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(self.read(), "[setting]\r\nadshow=0\r\n")

    def test_enable_overrides_explicit_one_and_restores_it(self) -> None:
        self.write(b"[setting]\r\nAdShow = 1\r\n")

        apply_ldplayer_data_ini(self.path, True)
        self.assertEqual(
            self.read(),
            "[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:1,launchadshow:-\r\n",
        )

        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(self.read(), "[setting]\r\nadshow=1\r\n")

    def test_enable_does_nothing_when_channel_already_off(self) -> None:
        self.write(b"[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n")

        self.assertFalse(apply_ldplayer_data_ini(self.path, True))
        self.assertNotIn(LDPLAYER_MARKER_KEY, self.read())

    def test_re_enable_does_not_overwrite_recorded_originals(self) -> None:
        """用户手动把键改回 1 后再启动，模式要重新压成 0，但记录的原值不能变成 0。"""
        self.write(b"[setting]\r\n")
        apply_ldplayer_data_ini(self.path, True)
        self.write(
            self.read().replace("adshow=0\r\nlaunch", "adshow=1\r\nlaunch").encode()
        )

        self.assertTrue(apply_ldplayer_data_ini(self.path, True))
        self.assertIn("adshow=0\r\n", self.read())
        self.assertIn(f"{LDPLAYER_MARKER_KEY}=adshow:-,launchadshow:-", self.read())

        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(self.read(), "[setting]\r\n")

    def test_keys_outside_setting_section_are_ignored(self) -> None:
        self.write(b"[other]\r\nadshow=0\r\n[setting]\r\n")

        apply_ldplayer_data_ini(self.path, True)
        self.assertEqual(
            self.read(),
            "[other]\r\nadshow=0\r\n[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:-,launchadshow:-\r\n",
        )

    def test_missing_section_and_file(self) -> None:
        self.assertTrue(apply_ldplayer_data_ini(self.path, True))
        self.assertEqual(
            self.read(),
            "[setting]\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:-,launchadshow:-\r\n",
        )

        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(self.read(), "[setting]\r\n")

    def test_utf16_file_keeps_bom_and_encoding(self) -> None:
        self.write("[setting]\r\ntitle=定制版\r\n".encode("utf-16"))

        apply_ldplayer_data_ini(self.path, True)
        raw = self.path.read_bytes()
        self.assertTrue(raw.startswith(b"\xff\xfe"))
        self.assertEqual(
            raw.decode("utf-16"),
            "[setting]\r\ntitle=定制版\r\nadshow=0\r\nlaunchadshow=0\r\n"
            f"{LDPLAYER_MARKER_KEY}=adshow:-,launchadshow:-\r\n",
        )

        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(
            self.path.read_bytes().decode("utf-16"), "[setting]\r\ntitle=定制版\r\n"
        )

    def test_non_ascii_bytes_survive_round_trip(self) -> None:
        """GBK 写的 ``title`` 不能被转码坏掉。"""
        raw = "[setting]\r\ntitle=明日方舟\r\n".encode("gbk")
        self.write(raw)

        apply_ldplayer_data_ini(self.path, True)
        apply_ldplayer_data_ini(self.path, False)
        self.assertEqual(self.path.read_bytes(), raw)


class SplashPlaceholderTest(unittest.TestCase):
    """MuMu 宿主缓存占位：目录换成同名空文件，撤销时只删自己放的文件。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "ProgramAds"

    def test_enable_replaces_directory_and_is_idempotent(self) -> None:
        self.target.mkdir()
        (self.target / "programAds.json").write_text("{}")

        self.assertTrue(apply_splash_placeholders([self.target], True))
        self.assertTrue(self.target.is_file())
        self.assertFalse(apply_splash_placeholders([self.target], True))

    def test_disable_removes_only_our_file(self) -> None:
        self.target.touch()
        self.assertTrue(apply_splash_placeholders([self.target], False))
        self.assertFalse(self.target.exists())

        self.target.mkdir()
        self.assertFalse(apply_splash_placeholders([self.target], False))
        self.assertTrue(self.target.is_dir())


class ApplyHostModeTest(unittest.TestCase):
    """按安装类型分发到各自的宿主层处理。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_ldplayer_writes_data_ini_next_to_manager(self) -> None:
        exe = self.root / "LDPlayer14" / "ldconsole.exe"
        exe.parent.joinpath("data").mkdir(parents=True)

        self.assertTrue(apply_host_mode("ldplayer", exe, True))
        self.assertIn("launchadshow=0", (exe.parent / "data" / "data.ini").read_text())

    def test_ldplayer_without_manager_does_nothing(self) -> None:
        self.assertFalse(apply_host_mode("ldplayer", None, True))

    def test_mumu_uses_placeholders(self) -> None:
        ads = self.root / "data" / "ProgramAds"
        ads.mkdir(parents=True)
        with mock.patch.object(
            master_mode, "mumu_splash_placeholder_paths", return_value=[ads]
        ):
            self.assertTrue(apply_host_mode("mumu", None, True))
        self.assertTrue(ads.is_file())

    def test_unknown_type_is_ignored(self) -> None:
        self.assertFalse(apply_host_mode("bluestacks", None, True))
