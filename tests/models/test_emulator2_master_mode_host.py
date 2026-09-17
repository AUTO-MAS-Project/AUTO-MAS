import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.utils.emulator2 import master_mode
from app.utils.emulator2.master_mode import (
    LDPLAYER_MARKER_KEY,
    LDPLAYER_OFF_SUFFIX,
    apply_host_mode,
    apply_ldplayer_data_ini,
    apply_ldplayer_partner,
    apply_splash_placeholders,
    ldplayer_data_ini_path,
    ldplayer_partner_exes,
    mumu_splash_placeholder_paths,
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


class PartnerExeTest(unittest.TestCase):
    """雷电桌面弹窗程序：原件和 ``partnername.data`` 指向的副本一起改名，关闭时改回。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.install = Path(self._tmp.name) / "LDPlayer14"
        self.install.mkdir()
        self.original = self.install / "ldplayerpartner.exe"
        self.copy = self.install / "ld20710.exe"
        self.original_off = self.install / ("ldplayerpartner.exe" + LDPLAYER_OFF_SUFFIX)
        self.copy_off = self.install / ("ld20710.exe" + LDPLAYER_OFF_SUFFIX)

    def name_file(self, raw: bytes) -> None:
        (self.install / "partnername.data").write_bytes(raw)

    def both_present(self) -> None:
        self.name_file("ld20710.exe".encode("utf-16-le"))
        self.original.write_bytes(b"exe")
        self.copy.write_bytes(b"exe")

    def test_copy_name_is_read_from_name_file(self) -> None:
        """实机的 ``partnername.data`` 是 22 B 的 UTF-16LE，没有 BOM 也没有换行。"""
        self.name_file("ld20710.exe".encode("utf-16-le"))
        self.assertEqual(
            ldplayer_partner_exes(self.install), [self.original, self.copy]
        )

        self.name_file("ld20710.exe\r\n".encode("utf-16"))  # 带 BOM 带换行
        self.assertEqual(
            ldplayer_partner_exes(self.install), [self.original, self.copy]
        )

        self.name_file(b"ld20710.exe")  # 纯 ASCII
        self.assertEqual(
            ldplayer_partner_exes(self.install), [self.original, self.copy]
        )

    def test_missing_or_odd_name_file_falls_back_to_original_only(self) -> None:
        self.assertEqual(ldplayer_partner_exes(self.install), [self.original])
        for raw in (
            b"",
            "sub/ld20710.exe".encode("utf-16-le"),
            "notes.txt".encode("utf-16-le"),
            "LDPlayerPartner.exe".encode("utf-16-le"),  # 指回原件本身，不重复处理
        ):
            self.name_file(raw)
            self.assertEqual(ldplayer_partner_exes(self.install), [self.original], raw)

    def test_enable_renames_both_and_is_idempotent(self) -> None:
        self.both_present()

        self.assertTrue(apply_ldplayer_partner(self.install, True))
        self.assertFalse(self.original.exists())
        self.assertFalse(self.copy.exists())
        self.assertTrue(self.original_off.is_file())
        self.assertTrue(self.copy_off.is_file())

        self.assertFalse(apply_ldplayer_partner(self.install, True))

    def test_disable_renames_back_and_is_idempotent(self) -> None:
        self.both_present()
        apply_ldplayer_partner(self.install, True)

        self.assertTrue(apply_ldplayer_partner(self.install, False))
        self.assertEqual(self.original.read_bytes(), b"exe")
        self.assertEqual(self.copy.read_bytes(), b"exe")
        self.assertFalse(self.original_off.exists())
        self.assertFalse(self.copy_off.exists())

        self.assertFalse(apply_ldplayer_partner(self.install, False))

    def test_disable_never_touches_files_we_did_not_rename(self) -> None:
        self.both_present()

        self.assertFalse(apply_ldplayer_partner(self.install, False))
        self.assertTrue(self.original.is_file())
        self.assertTrue(self.copy.is_file())

    def test_upgrade_re_extracted_exe_replaces_stale_renamed_copy(self) -> None:
        """雷电升级重新释放原名后再开模式：新件顶掉旧的改名件，留下的始终是最新版。"""
        self.both_present()
        apply_ldplayer_partner(self.install, True)
        self.original.write_bytes(b"new")

        self.assertTrue(apply_ldplayer_partner(self.install, True))
        self.assertFalse(self.original.exists())
        self.assertEqual(self.original_off.read_bytes(), b"new")

    def test_disable_after_upgrade_drops_stale_renamed_copy(self) -> None:
        self.both_present()
        apply_ldplayer_partner(self.install, True)
        self.original.write_bytes(b"new")

        self.assertTrue(apply_ldplayer_partner(self.install, False))
        self.assertEqual(self.original.read_bytes(), b"new")
        self.assertFalse(self.original_off.exists())
        self.assertEqual(self.copy.read_bytes(), b"exe")

    def test_failure_on_one_file_does_not_stop_the_other(self) -> None:
        self.both_present()
        real_replace = master_mode.os.replace

        def flaky_replace(src, dst):
            if Path(src).name == "ldplayerpartner.exe":
                raise PermissionError("in use")
            real_replace(src, dst)

        with mock.patch.object(master_mode.os, "replace", side_effect=flaky_replace):
            self.assertTrue(apply_ldplayer_partner(self.install, True))
        self.assertTrue(self.original.is_file())
        self.assertTrue(self.copy_off.is_file())


class SplashPlaceholderTest(unittest.TestCase):
    """MuMu 宿主缓存占位：目录换成同名空文件，撤销时只删自己放的文件。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "ProgramAds"

    def test_only_program_ads_is_placeholdered(self) -> None:
        """实例开屏图目录 MuMu 启动时会连占位文件一起重建，不再占。"""
        appdata = Path(self._tmp.name) / "Roaming"
        self.assertEqual(
            mumu_splash_placeholder_paths(appdata),
            [appdata / "Netease" / "MuMuPlayer" / "data" / "ProgramAds"],
        )

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

    def test_ldplayer_renames_partner_exe_in_the_same_directory(self) -> None:
        exe = self.root / "LDPlayer14" / "ldconsole.exe"
        exe.parent.joinpath("data").mkdir(parents=True)
        partner = exe.parent / "ldplayerpartner.exe"
        partner.write_bytes(b"exe")

        self.assertTrue(apply_host_mode("ldplayer", exe, True))
        self.assertFalse(partner.exists())
        self.assertTrue(partner.with_name(partner.name + LDPLAYER_OFF_SUFFIX).is_file())

        self.assertTrue(apply_host_mode("ldplayer", exe, False))
        self.assertTrue(partner.is_file())
        self.assertNotIn(
            LDPLAYER_MARKER_KEY, (exe.parent / "data" / "data.ini").read_text()
        )

    def test_ldplayer_data_ini_failure_does_not_block_partner_exe(self) -> None:
        exe = self.root / "LDPlayer14" / "ldconsole.exe"
        exe.parent.mkdir(parents=True)
        partner = exe.parent / "ldplayerpartner.exe"
        partner.write_bytes(b"exe")

        with mock.patch.object(
            master_mode, "apply_ldplayer_data_ini", side_effect=PermissionError("ro")
        ):
            self.assertTrue(apply_host_mode("ldplayer", exe, True))
        self.assertFalse(partner.exists())

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
