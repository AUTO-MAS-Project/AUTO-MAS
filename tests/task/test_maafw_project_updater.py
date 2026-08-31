import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app.core  # noqa: F401  (initialise app before importing task modules)

from app.task.MaaFW.tools import project_updater as pu
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    updater as core_updater,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateError,
    _normalise_package_source,
    _select_github_release_asset,
    discover_maafw_project_update,
)


class _FakeInterface:
    def __init__(self, *, rid="RID", github="", multiplatform=False, version="1.0.0"):
        self.mirrorchyan_rid = rid
        self.mirrorchyan_multiplatform = multiplatform
        self.github = github
        self.version = version
        self.name = "Demo"


class RecycledVersionCompareTest(unittest.TestCase):
    def test_remote_newer_semver(self):
        self.assertTrue(pu._is_remote_newer("2.0.0", "1.9.9"))
        self.assertTrue(pu._is_remote_newer("1.10.0", "1.9.0"))
        self.assertFalse(pu._is_remote_newer("1.0.0", "1.0.0"))
        self.assertFalse(pu._is_remote_newer("1.0.0", "2.0.0"))

    def test_remote_newer_ignores_v_prefix(self):
        self.assertFalse(pu._is_remote_newer("v1.0.0", "1.0.0"))
        self.assertTrue(pu._is_remote_newer("v2.0.0", "1.0.0"))

    def test_remote_newer_edge_cases(self):
        self.assertFalse(pu._is_remote_newer("", "1.0.0"))
        self.assertTrue(pu._is_remote_newer("1.0.0", ""))
        # non-PEP440 tags fall back to string inequality
        self.assertTrue(pu._is_remote_newer("build-b", "build-a"))
        self.assertFalse(pu._is_remote_newer("build-a", "build-a"))

    def test_normalize_version_strips_v(self):
        self.assertEqual(pu._normalize_version("  V1.2.3 "), "1.2.3")
        self.assertEqual(pu._normalize_version("v0"), "0")


class RecycledRepoParseTest(unittest.TestCase):
    def test_parse_full_url(self):
        self.assertEqual(
            pu._parse_github_repo("https://github.com/Owner/Repo"), ("Owner", "Repo")
        )
        self.assertEqual(
            pu._parse_github_repo("https://github.com/Owner/Repo.git"),
            ("Owner", "Repo"),
        )

    def test_parse_short_form(self):
        self.assertEqual(pu._parse_github_repo("Owner/Repo"), ("Owner", "Repo"))

    def test_parse_rejects_non_github(self):
        self.assertIsNone(pu._parse_github_repo("https://gitlab.com/a/b"))
        self.assertIsNone(pu._parse_github_repo("not-a-repo"))


class RecycledAssetSelectionTest(unittest.TestCase):
    def _assets(self):
        return [
            {
                "name": "Demo-linux-x64.zip",
                "browser_download_url": "https://x/linux.zip",
            },
            {"name": "Demo-win-x64.zip", "browser_download_url": "https://x/win.zip"},
            {"name": "notes.txt", "browser_download_url": "https://x/notes.txt"},
        ]

    def test_prefers_windows_x64_zip(self):
        url = pu._select_github_asset(self._assets(), "Demo")
        self.assertEqual(url, "https://x/win.zip")

    def test_pattern_filters_candidates(self):
        url = pu._select_github_asset(self._assets(), "Demo", pattern="*linux*.zip")
        self.assertEqual(url, "https://x/linux.zip")

    def test_no_zip_returns_none(self):
        assets = [{"name": "a.txt", "browser_download_url": "https://x/a.txt"}]
        self.assertIsNone(pu._select_github_asset(assets, "Demo"))


class ShellFamilyAssetDisambiguationTest(unittest.TestCase):
    """同版本按 UI 外壳分包（M9A 的 MFAA / MXU zip）时按外壳家族消歧。"""

    def _release(self):
        return {
            "assets": [
                {
                    "name": "M9A-win-x86_64-v4.7.0-MFAA.zip",
                    "browser_download_url": "https://x/M9A-MFAA.zip",
                },
                {
                    "name": "M9A-win-x86_64-v4.7.0-MXU.zip",
                    "browser_download_url": "https://x/M9A-MXU.zip",
                },
            ]
        }

    def _select(self, shell_hint: str):
        return _select_github_release_asset(
            self._release(),
            r"\.zip$",
            project_name="M9A",
            project_shell_hint=shell_hint,
            prefer_windows_x64=True,
        )

    def test_mfaavalonia_family_selects_mfaa_package(self):
        url, reason = self._select("MFAAvalonia")
        self.assertEqual(url, "https://x/M9A-MFAA.zip")
        self.assertEqual(reason, "")

    def test_mxu_family_selects_mxu_package(self):
        url, reason = self._select("MXU")
        self.assertEqual(url, "https://x/M9A-MXU.zip")
        self.assertEqual(reason, "")

    def test_unknown_family_stays_ambiguous(self):
        url, reason = self._select("unknown")
        self.assertIsNone(url)
        self.assertIn("ambiguous", reason)
        self.assertIn("MFAA.zip", reason)
        self.assertIn("MXU.zip", reason)

    def test_absent_hint_stays_ambiguous(self):
        url, reason = self._select("")
        self.assertIsNone(url)
        self.assertIn("ambiguous", reason)

    def test_hint_does_not_override_unique_project_match(self):
        release = {
            "assets": [
                {
                    "name": "M9A-win-x86_64-v4.7.0-MFAA.zip",
                    "browser_download_url": "https://x/m9a.zip",
                },
                {
                    "name": "MaaYY-win-x86_64-v4.7.0-MXU.zip",
                    "browser_download_url": "https://x/other.zip",
                },
            ]
        }
        # 项目名已唯一确定，即便外壳提示指向另一个包也不改变结果。
        url, reason = _select_github_release_asset(
            release,
            r"\.zip$",
            project_name="M9A",
            project_shell_hint="MXU",
            prefer_windows_x64=True,
        )
        self.assertEqual(url, "https://x/m9a.zip")
        self.assertEqual(reason, "")


class ProviderSelectionTest(unittest.TestCase):
    def test_compat_source_config_normalises_provider(self):
        self.assertEqual(
            pu._compat_source_config(
                "",
                mirror_cdk="",
                channel="",
                github_repo="",
                github_tag="",
                github_asset_pattern="",
            )["source"],
            "mirrorchyan",
        )
        self.assertEqual(
            pu._compat_source_config(
                "MirrorChyan",
                mirror_cdk="c",
                channel="stable",
                github_repo="",
                github_tag="",
                github_asset_pattern="",
            )["source"],
            "mirrorchyan",
        )
        gh = pu._compat_source_config(
            "GitHub",
            mirror_cdk="",
            channel="beta",
            github_repo="a/b",
            github_tag="v1",
            github_asset_pattern="*.zip",
        )
        self.assertEqual(gh["source"], "github_release")
        self.assertEqual(gh["repo"], "a/b")
        self.assertEqual(gh["tag"], "v1")
        self.assertEqual(gh["asset_pattern"], "*.zip")
        self.assertEqual(gh["channel"], "beta")

    def test_core_normalise_package_source(self):
        self.assertEqual(_normalise_package_source(""), "mirrorchyan")
        self.assertEqual(_normalise_package_source("MirrorChyan"), "mirrorchyan")
        self.assertEqual(_normalise_package_source("GitHub"), "github_release")
        self.assertEqual(_normalise_package_source("github release"), "github_release")
        with self.assertRaises(MaaFWProjectUpdateError):
            _normalise_package_source("sourceforge")


class DiscoveryRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_mirrorchyan_source_never_calls_github(self):
        candidate = MaaFWProjectUpdateCandidate(
            source="mirrorchyan", version="2.0.0", download_url="https://x/y.zip"
        )
        mirror_discovery = MaaFWProjectUpdateDiscovery(
            source="mirrorchyan", version="2.0.0", candidate=candidate
        )
        with (
            patch.object(
                core_updater,
                "_check_mirrorchyan_update",
                AsyncMock(return_value=mirror_discovery),
            ),
            patch.object(
                core_updater, "_check_github_release_update", AsyncMock()
            ) as github_mock,
        ):
            result = await discover_maafw_project_update(
                _FakeInterface(),
                current_version="1.0.0",
                source_config={"package_source": "mirrorchyan", "mirror_cdk": "cdk"},
            )
        self.assertIs(result, mirror_discovery)
        github_mock.assert_not_awaited()

    async def test_github_source_resolves_exact_mirror_target(self):
        mirror_discovery = MaaFWProjectUpdateDiscovery(
            source="mirrorchyan", version="2.0.0"
        )
        github_candidate = MaaFWProjectUpdateCandidate(
            source="github_release", version="v2.0.0", download_url="https://x/gh.zip"
        )
        github_discovery = MaaFWProjectUpdateDiscovery(
            source="github_release", version="v2.0.0", candidate=github_candidate
        )
        with (
            patch.object(
                core_updater,
                "_check_mirrorchyan_update",
                AsyncMock(return_value=mirror_discovery),
            ),
            patch.object(
                core_updater,
                "_check_github_release_update",
                AsyncMock(return_value=github_discovery),
            ) as github_mock,
        ):
            result = await discover_maafw_project_update(
                _FakeInterface(github="owner/repo"),
                current_version="1.0.0",
                source_config={
                    "package_source": "github_release",
                    "repo": "owner/repo",
                },
            )
        github_mock.assert_awaited_once()
        self.assertEqual(github_mock.await_args.kwargs["target_version"], "2.0.0")
        self.assertEqual(result.source, "mirrorchyan")
        self.assertEqual(result.candidate.version, "2.0.0")

    async def test_no_mirror_rid_skips_update(self):
        result = await discover_maafw_project_update(
            _FakeInterface(rid=""),
            current_version="1.0.0",
            source_config={"package_source": "mirrorchyan"},
        )
        self.assertIsNone(result)


class ApplyPathShellHintInjectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_update_if_needed_injects_shell_hint_from_project_root(self):
        captured = {}

        async def _fake_discover(interface_model, **kwargs):
            captured.update(kwargs)
            return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("MFAAvalonia.dll", "appsettings.json", "interface.json"):
                (root / name).write_text("", encoding="utf-8")
            with patch.object(pu, "_core_discover_update", _fake_discover):
                await pu.update_maafw_project_if_needed(
                    root, _FakeInterface(), source="GitHub", github_repo="owner/repo"
                )
        self.assertEqual(
            captured["source_config"].get("project_shell_hint"), "MFAAvalonia"
        )


if __name__ == "__main__":
    unittest.main()
