import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.wuthering_waves import (
    WutheringWavesLocalState,
    _parse_update_payload,
    read_wuthering_waves_local_state,
)


def _write_state(install_dir: Path, **payload: object) -> None:
    (install_dir / "launcherDownloadConfig.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class LocalStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.install_dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_missing_file_raises_instead_of_reporting_latest(self) -> None:
        # 版本记录缺失绝不能退化成"已是最新"，否则会静默启动旧版客户端
        with self.assertRaises(FileNotFoundError):
            read_wuthering_waves_local_state(self.install_dir)

    def test_missing_version_field_raises(self) -> None:
        _write_state(self.install_dir, state="", isPreDownload=False)
        with self.assertRaises(ValueError):
            read_wuthering_waves_local_state(self.install_dir)

    def test_unparsable_file_raises(self) -> None:
        (self.install_dir / "launcherDownloadConfig.json").write_text(
            "{not json", encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            read_wuthering_waves_local_state(self.install_dir)

    def test_parses_real_launcher_payload(self) -> None:
        _write_state(
            self.install_dir,
            version="3.6.0",
            reUseVersion="",
            state="",
            isPreDownload=False,
            appId="10003",
        )
        state = read_wuthering_waves_local_state(self.install_dir)
        self.assertEqual(state.version, "3.6.0")
        self.assertTrue(state.is_idle)

    def test_non_empty_state_is_not_idle(self) -> None:
        # state 非空说明启动器仍在下载/解压，此时的 version 不代表已落盘
        self.assertFalse(
            WutheringWavesLocalState(
                version="3.6.0", state="downloading", is_predownload=False
            ).is_idle
        )

    def test_predownload_flag_is_not_idle(self) -> None:
        self.assertFalse(
            WutheringWavesLocalState(
                version="3.7.0", state="", is_predownload=True
            ).is_idle
        )


class ParseUpdatePayloadTest(unittest.TestCase):
    install_dir = Path("C:/game")

    def _parse(self, payload: object, local_version: str = "3.6.0"):
        return _parse_update_payload(
            payload,
            install_dir=self.install_dir,
            local_version=local_version,
            api_url="https://example.invalid/index.json",
        )

    def test_same_version_needs_no_update(self) -> None:
        info = self._parse({"default": {"version": "3.6.0"}})
        self.assertFalse(info.update_available)
        self.assertFalse(info.predownload_available)

    def test_version_mismatch_needs_update(self) -> None:
        info = self._parse({"default": {"version": "3.7.0"}})
        self.assertTrue(info.update_available)
        self.assertEqual(info.release_version, "3.7.0")

    def test_rollback_also_counts_as_update(self) -> None:
        # 与官方启动器一致：版本号不等即需处理，不假设官方只会升版本
        self.assertTrue(self._parse({"default": {"version": "3.5.3"}}).update_available)

    def test_missing_predownload_key_is_not_available(self) -> None:
        # 非预下载窗口期整个 predownload 键都不下发，只有 predownloadSwitch
        info = self._parse({"default": {"version": "3.6.0"}, "predownloadSwitch": 1})
        self.assertIsNone(info.predownload_version)
        self.assertFalse(info.predownload_available)

    def test_predownload_available_when_window_open(self) -> None:
        info = self._parse(
            {
                "default": {"version": "3.6.0"},
                "predownload": {"version": "3.7.0"},
                "predownloadSwitch": 1,
            }
        )
        self.assertTrue(info.predownload_available)

    def test_predownload_ignored_when_switch_off(self) -> None:
        info = self._parse(
            {
                "default": {"version": "3.6.0"},
                "predownload": {"version": "3.7.0"},
                "predownloadSwitch": 0,
            }
        )
        self.assertFalse(info.predownload_available)

    def test_predownload_yields_to_pending_update(self) -> None:
        # 正式更新未做完时不该分心去预下载
        info = self._parse(
            {
                "default": {"version": "3.7.0"},
                "predownload": {"version": "3.8.0"},
                "predownloadSwitch": 1,
            }
        )
        self.assertTrue(info.update_available)
        self.assertFalse(info.predownload_available)

    def test_malformed_payload_raises(self) -> None:
        for payload in ([], {}, {"default": {}}, {"default": {"version": ""}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self._parse(payload)


if __name__ == "__main__":
    unittest.main()
