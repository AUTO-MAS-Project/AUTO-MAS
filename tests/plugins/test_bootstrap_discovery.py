from __future__ import annotations

import importlib.metadata as importlib_metadata
import importlib.util
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Iterable


def _load_pypi_site_module():
    """直接按文件路径加载 app/plugins/pypi_site.py 模块。

    这样可以绕开 app/plugins/__init__.py 的副作用导入链 (依赖 typing.Unpack,
    在 Python 3.11+ 才可用), 让本测试模块在仅装最小依赖的 Python 3.10 解释器
    下也能运行, 同时更接近单元测试的隔离要求。

    生产集成测试 (阶段 6) 会通过 uv venv (Python 3.12) 走完整 import 路径,
    覆盖 __init__.py 副作用导入链。
    """
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "app" / "plugins" / "pypi_site.py"
    spec = importlib.util.spec_from_file_location(
        "_pypi_site_under_test", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 注册到 sys.modules, 使 invalidate_entry_points_cache 内部的
    # _entry_points_cache.clear() 能正确清空本模块级变量。
    sys.modules["_pypi_site_under_test"] = module
    return module


_pypi_site = _load_pypi_site_module()

ENTRY_POINT_GROUPS = _pypi_site.ENTRY_POINT_GROUPS
InstalledPluginEntryPoint = _pypi_site.InstalledPluginEntryPoint
iter_plugin_entry_points = _pypi_site.iter_plugin_entry_points
get_installed_plugin_entry_points = _pypi_site.get_installed_plugin_entry_points
invalidate_entry_points_cache = _pypi_site.invalidate_entry_points_cache
ensure_pypi_site_packages_on_syspath = (
    _pypi_site.ensure_pypi_site_packages_on_syspath
)


# 期望的插件矩阵: (plugin_name, distribution_name, version, entry_point_group)
# 与 pyproject.toml [tool.auto-mas.plugin-bootstrap].packages 对齐。
# 聚合包 (automas-hsr, automas-m9a) 无 entry point, 不在此列表。
EXPECTED_BOOTSTRAP_PLUGINS: list[tuple[str, str, str, str]] = [
    # 宿主工程内建插件 (workspace)
    ("auto_mas_core", "auto-mas-core", "6.0.0a1", "auto_mas.plugins"),
    ("ok_script_adapter", "automas-plugin-ok-script-adapter", "0.1.1", "auto_mas.plugins"),
    ("okww_adapter", "automas-plugin-okww-adapter", "0.0.2", "auto_mas.plugins"),
    ("browser", "automas-plugin-browser", "0.1.0", "auto_mas.plugins"),
    # MaaFW 官方包
    ("automas_maafw_interface", "automas-maafw-interface", "0.2.0", "auto_mas.plugins"),
    ("automas_maafw_agent_env", "automas-maafw-agent-env", "0.1.1", "auto_mas.plugins"),
    ("automas_maafw_controller_adb", "automas-maafw-controller-adb", "0.1.0", "auto_mas.plugins"),
    (
        "automas_maafw_controller_win32",
        "automas-maafw-controller-win32",
        "0.1.1",
        "auto_mas.plugins",
    ),
    ("automas_maafw_project_update", "automas-maafw-project-update", "0.1.1", "auto_mas.plugins"),
    # MaaFW 本地草稿 (managed ecosystem)
    ("automas_maafw_project_store", "automas-maafw-project-store", "0.1.0", "auto_mas.plugins"),
    ("automas_maafw_runtime_pool", "automas-maafw-runtime-pool", "0.1.0", "auto_mas.plugins"),
    ("automas_maafw_runner", "automas-maafw-runner", "0.3.1", "auto_mas.plugins"),
    ("automas_script_maafw", "automas-script-maafw", "0.1.7", "auto_mas.plugins"),
    ("automas_script_maafw_managed", "automas-script-maafw-managed", "0.1.2", "auto_mas.plugins"),
    # M9A pack
    (
        "automas_script_maafw_pack_m9a",
        "automas-script-maafw-pack-m9a",
        "0.1.2",
        "auto_mas.plugins",
    ),
    # HSR core + adapters
    ("automas_script_hsr", "automas-script-hsr", "0.1.5", "auto_mas.plugins"),
    ("automas_hsr_adapter_sra", "automas-hsr-adapter-sra", "0.1.5", "auto_mas.plugins"),
    ("automas_hsr_adapter_m7a", "automas-hsr-adapter-m7a", "0.1.6", "auto_mas.plugins"),
    # 其他 AUTO-MAS 官方独立插件仓库
    ("mxu_import", "automas-plugin-mxu-import", "0.1.0", "auto_mas.plugins"),
    (
        "maaend_adapter",
        "automas_plugin_maaend_adapter",
        "0.0.3",
        "auto_mas.plugins",
    ),
    ("script_MAA", "automas_script_maa", "0.0.6", "auto_mas.plugins"),
]


# 宿主内建插件, 不在 [tool.auto-mas.plugin-bootstrap].packages 中显式声明:
# - auto_mas_core 由前端 pluginBootstrapService.SYSTEM_BOOTSTRAP_PACKAGES 单独硬编码安装
# - browser 同样由前端 pluginBootstrapService.SYSTEM_BOOTSTRAP_PACKAGES 安装
# 两者均会与 bootstrap 包一起进入 site-packages, 因此仍参与 IterPluginEntryPointsTest
# 的发现验证, 但不参与 BootstrapConfigConsistencyTest 的 bootstrap packages 声明验证。
SYSTEM_OR_WORKSPACE_PLUGIN_NAMES: set[str] = {"auto_mas_core", "browser"}

# 在 bootstrap packages 中以字符串形式声明 (不带 version) 的 workspace 包.
# 这些包的版本由 [tool.uv.sources] 中 { workspace = true } 决定,
# 在 bootstrap packages 中不重复声明 version, 否则会与 workspace 版本冲突.
# test_pyproject_declares_expected_versions 跳过这些包的 version 检查.
WORKSPACE_PLUGIN_WITH_UNPINNED_VERSION: set[str] = {
    "ok_script_adapter",
    "okww_adapter",
}


def _normalize_dist_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def _create_fake_dist_info(
    site_dir: Path,
    distribution_name: str,
    version: str,
    entry_point_group: str,
    entry_point_name: str,
    entry_point_value: str | None = None,
) -> Path:
    """在临时 site-packages 目录下创建一个伪造的 .dist-info 目录。"""
    normalized = _normalize_dist_name(distribution_name)
    dist_info_dir = site_dir / f"{normalized}-{version}.dist-info"
    dist_info_dir.mkdir(parents=True, exist_ok=True)

    # METADATA 文件 (importlib.metadata 需要它来识别 distribution)
    metadata_content = textwrap.dedent(
        f"""\
        Metadata-Version: 2.1
        Name: {distribution_name}
        Version: {version}
        """
    )
    (dist_info_dir / "METADATA").write_text(metadata_content, encoding="utf-8")

    # entry_points.txt
    value = entry_point_value or f"{entry_point_name.replace('-', '_')}.plugin:Plugin"
    entry_points_content = f"[{entry_point_group}]\n{entry_point_name} = {value}\n"
    (dist_info_dir / "entry_points.txt").write_text(entry_points_content, encoding="utf-8")

    # RECORD 文件 (某些 importlib.metadata 实现需要)
    record_content = f"{normalized}/__init__.py,,\n{dist_info_dir.name}/METADATA,,\n{dist_info_dir.name}/entry_points.txt,,\n"
    (dist_info_dir / "RECORD").write_text(record_content, encoding="utf-8")

    # 创建一个空的包目录,使 importlib.metadata 能找到 distribution
    package_dir = site_dir / normalized.replace(".", "_")
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    return dist_info_dir


def _create_fake_site_packages(
    plugins_dir: Path,
    plugins: Iterable[tuple[str, str, str, str]],
) -> Path:
    """构造一个完整的假 site-packages 目录,包含所有给定插件的 .dist-info。"""
    site_dir = plugins_dir / "pypi" / "site-packages"
    site_dir.mkdir(parents=True, exist_ok=True)
    for entry_name, dist_name, version, group in plugins:
        _create_fake_dist_info(
            site_dir=site_dir,
            distribution_name=dist_name,
            version=version,
            entry_point_group=group,
            entry_point_name=entry_name,
        )
    return site_dir


class IterPluginEntryPointsTest(unittest.TestCase):
    """验证 iter_plugin_entry_points 能从本地 site-packages 发现所有声明的插件入口点。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.temp_dir.name) / "plugins"
        self.site_dir = _create_fake_site_packages(self.plugins_dir, EXPECTED_BOOTSTRAP_PLUGINS)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_discovers_all_expected_entry_points(self) -> None:
        entry_points = iter_plugin_entry_points(self.plugins_dir)

        discovered_names = {ep.name for ep in entry_points}
        expected_names = {plugin_name for plugin_name, _, _, _ in EXPECTED_BOOTSTRAP_PLUGINS}
        missing = expected_names - discovered_names
        self.assertEqual(
            missing,
            set(),
            f"未发现的插件入口点: {sorted(missing)}",
        )

    def test_only_returns_supported_groups(self) -> None:
        entry_points = iter_plugin_entry_points(self.plugins_dir)
        for ep in entry_points:
            self.assertIn(
                ep.group,
                ENTRY_POINT_GROUPS,
                f"入口点 {ep.name} 使用了未支持的 group: {ep.group}",
            )

    def test_returns_distribution_and_version(self) -> None:
        entry_points = iter_plugin_entry_points(self.plugins_dir)
        by_name = {ep.name: ep for ep in entry_points}

        for plugin_name, expected_dist, expected_version, _ in EXPECTED_BOOTSTRAP_PLUGINS:
            ep = by_name.get(plugin_name)
            self.assertIsNotNone(ep, f"未发现入口点: {plugin_name}")
            dist = getattr(ep, "dist", None)
            self.assertIsNotNone(dist, f"入口点 {plugin_name} 缺少 distribution")
            actual_dist = getattr(dist, "name", None)
            actual_version = getattr(dist, "version", None)
            self.assertEqual(
                _normalize_dist_name(actual_dist or ""),
                _normalize_dist_name(expected_dist),
                f"入口点 {plugin_name} distribution 不匹配: 期望={expected_dist}, 实际={actual_dist}",
            )
            self.assertEqual(
                actual_version,
                expected_version,
                f"入口点 {plugin_name} 版本不匹配: 期望={expected_version}, 实际={actual_version}",
            )

    def test_deduplicates_entry_points(self) -> None:
        # 在已有插件基础上,再创建一个同 distribution 的重复 .dist-info
        _create_fake_dist_info(
            site_dir=self.site_dir,
            distribution_name="automas-script-hsr",
            version="0.1.0",
            entry_point_group="auto_mas.plugins",
            entry_point_name="automas_script_hsr",
        )
        invalidate_entry_points_cache()

        entry_points = iter_plugin_entry_points(self.plugins_dir)
        hsr_eps = [ep for ep in entry_points if ep.name == "automas_script_hsr"]
        self.assertEqual(
            len(hsr_eps),
            1,
            f"automas_script_hsr 入口点应去重为 1, 实际 {len(hsr_eps)}",
        )

    def test_ignores_unsupported_group(self) -> None:
        _create_fake_dist_info(
            site_dir=self.site_dir,
            distribution_name="some-other-package",
            version="1.0.0",
            entry_point_group="console_scripts",
            entry_point_name="some_cli",
        )
        invalidate_entry_points_cache()

        entry_points = iter_plugin_entry_points(self.plugins_dir)
        names = {ep.name for ep in entry_points}
        self.assertNotIn("some_cli", names)

    def test_caches_until_site_dir_changes(self) -> None:
        invalidate_entry_points_cache()

        first = iter_plugin_entry_points(self.plugins_dir)
        first_count = len(first)

        # 第二次调用应命中缓存, 不重新扫描
        second = iter_plugin_entry_points(self.plugins_dir)
        self.assertEqual(len(second), first_count)

        # 添加新 dist-info 后, mtime 变化, 缓存失效
        _create_fake_dist_info(
            site_dir=self.site_dir,
            distribution_name="brand-new-plugin",
            version="0.0.1",
            entry_point_group="auto_mas.plugins",
            entry_point_name="brand_new_plugin",
        )
        third = iter_plugin_entry_points(self.plugins_dir)
        names = {ep.name for ep in third}
        self.assertIn("brand_new_plugin", names)


class GetInstalledPluginEntryPointsTest(unittest.TestCase):
    """验证 get_installed_plugin_entry_points 返回结构化的快照。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.temp_dir.name) / "plugins"
        self.site_dir = _create_fake_site_packages(self.plugins_dir, EXPECTED_BOOTSTRAP_PLUGINS)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_returns_grouped_by_entry_point_name(self) -> None:
        invalidate_entry_points_cache()

        snapshot = get_installed_plugin_entry_points(self.plugins_dir)

        self.assertIsInstance(snapshot, dict)
        for plugin_name, expected_dist, expected_version, expected_group in EXPECTED_BOOTSTRAP_PLUGINS:
            entries = snapshot.get(plugin_name)
            self.assertIsNotNone(entries, f"快照缺少插件: {plugin_name}")
            self.assertGreaterEqual(len(entries), 1)
            entry: InstalledPluginEntryPoint = entries[0]
            self.assertEqual(entry.name, plugin_name)
            self.assertEqual(entry.group, expected_group)
            self.assertEqual(
                _normalize_dist_name(entry.distribution or ""),
                _normalize_dist_name(expected_dist),
            )
            self.assertEqual(entry.version, expected_version)


class EditableImportRefreshTest(unittest.TestCase):
    """A local editable install must become importable in the same process."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.temp_dir.name) / "plugins"
        self.site_dir = self.plugins_dir / "pypi" / "site-packages"
        self.project_dir = Path(self.temp_dir.name) / "editable-project"
        self.import_dir = self.project_dir / "src"
        self.module_name = "same_process_editable_plugin"

    def tearDown(self) -> None:
        sys.modules.pop(self.module_name, None)
        normalized = str(self.import_dir.resolve())
        while normalized in sys.path:
            sys.path.remove(normalized)
        self.temp_dir.cleanup()

    def test_refreshes_new_editable_pth_after_initial_empty_scan(self) -> None:
        ensure_pypi_site_packages_on_syspath(self.plugins_dir)

        package_dir = self.import_dir / self.module_name
        package_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("VALUE = 'ready'\n", encoding="utf-8")
        (self.project_dir / "pyproject.toml").write_text(
            "[project]\nname = 'same-process-editable-plugin'\nversion = '1.0.0'\n",
            encoding="utf-8",
        )

        dist_info = self.site_dir / "same_process_editable_plugin-1.0.0.dist-info"
        dist_info.mkdir(parents=True)
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\n"
            "Name: same-process-editable-plugin\n"
            "Version: 1.0.0\n",
            encoding="utf-8",
        )
        (dist_info / "RECORD").write_text("", encoding="utf-8")
        (self.site_dir / "__editable__.same_process_editable_plugin-1.0.0.pth").write_text(
            f"{self.import_dir}\n",
            encoding="utf-8",
        )

        invalidate_entry_points_cache()
        ensure_pypi_site_packages_on_syspath(self.plugins_dir)

        imported = __import__(self.module_name)
        self.assertEqual(imported.VALUE, "ready")
        self.assertEqual(sys.path[0], str(self.import_dir.resolve()))


class BootstrapConfigConsistencyTest(unittest.TestCase):
    """验证 pyproject.toml [tool.auto-mas.plugin-bootstrap].packages 与期望的插件矩阵一致。"""

    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.pyproject_path = self.repo_root / "pyproject.toml"

    def _parse_bootstrap_packages(self) -> list[tuple[str, str | None]]:
        """从 pyproject.toml 手工解析 [tool.auto-mas.plugin-bootstrap].packages。"""
        content = self.pyproject_path.read_text(encoding="utf-8")
        marker = "[tool.auto-mas.plugin-bootstrap]"
        marker_idx = content.find(marker)
        self.assertGreater(marker_idx, -1, "pyproject.toml 缺少 [tool.auto-mas.plugin-bootstrap] 段")

        section_start = marker_idx + len(marker)
        rest = content[section_start:]
        next_section = rest.find("\n[")
        if next_section == -1:
            section_body = rest
        else:
            section_body = rest[:next_section]

        import re
        packages_match = re.search(r"packages\s*=\s*\[([\s\S]*?)\]", section_body)
        self.assertIsNotNone(packages_match, "bootstrap 段缺少 packages 数组")
        array_body = packages_match.group(1)

        # 简化分割: 按逗号切, 但要处理嵌套 {}
        items: list[str] = []
        depth = 0
        current = ""
        in_str = False
        str_char = ""
        for ch in array_body:
            if in_str:
                current += ch
                if ch == str_char:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                str_char = ch
                current += ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "," and depth == 0:
                trimmed = current.strip()
                if trimmed:
                    items.append(trimmed)
                current = ""
                continue
            current += ch
        last = current.strip()
        if last:
            items.append(last)

        result: list[tuple[str, str | None]] = []
        for item in items:
            if item.startswith(("{", '"', "'")) is False:
                continue
            if item.startswith(('"', "'")):
                name = item.strip('"\'').strip()
                result.append((name, None))
                continue
            # inline table
            name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', item)
            version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', item)
            self.assertIsNotNone(name_match, f"无法解析 inline table: {item}")
            name = name_match.group(1)
            version = version_match.group(1) if version_match else None
            result.append((name, version))
        return result

    def test_pyproject_contains_all_expected_packages(self) -> None:
        if not self.pyproject_path.exists():
            self.skipTest("pyproject.toml 不存在 (可能不在仓库根运行)")
        declared = self._parse_bootstrap_packages()
        declared_names = {_normalize_dist_name(name) for name, _ in declared}

        for plugin_name, expected_dist, _, _ in EXPECTED_BOOTSTRAP_PLUGINS:
            if plugin_name in SYSTEM_OR_WORKSPACE_PLUGIN_NAMES:
                # 系统/workspace 包走单独路径, 不应在 bootstrap packages 中声明
                continue
            normalized = _normalize_dist_name(expected_dist)
            self.assertIn(
                normalized,
                declared_names,
                f"pyproject.toml bootstrap 缺少 distribution: {expected_dist}",
            )

    def test_pyproject_declares_expected_versions(self) -> None:
        if not self.pyproject_path.exists():
            self.skipTest("pyproject.toml 不存在")
        declared = self._parse_bootstrap_packages()
        declared_by_name = {
            _normalize_dist_name(name): version for name, version in declared
        }

        for plugin_name, expected_dist, expected_version, _ in EXPECTED_BOOTSTRAP_PLUGINS:
            if plugin_name in SYSTEM_OR_WORKSPACE_PLUGIN_NAMES:
                continue
            if plugin_name in WORKSPACE_PLUGIN_WITH_UNPINNED_VERSION:
                # workspace 包版本由 [tool.uv.sources] 控制, bootstrap 中以字符串形式声明,
                # 不显式声明 version; 仅验证其存在 (已由 test_pyproject_contains_all_expected_packages 覆盖)
                continue
            normalized = _normalize_dist_name(expected_dist)
            actual_version = declared_by_name.get(normalized)
            self.assertIsNotNone(
                actual_version,
                f"bootstrap 未声明 {expected_dist} 的 version",
            )
            self.assertEqual(
                actual_version,
                expected_version,
                f"bootstrap 声明的 {expected_dist} 版本不匹配: 期望={expected_version}, 实际={actual_version}",
            )

    def test_system_or_workspace_packages_not_in_bootstrap_packages(self) -> None:
        """auto-mas-core 由前端 SYSTEM_BOOTSTRAP_PACKAGES 单独处理;
        automas-plugin-browser 也由前端 SYSTEM_BOOTSTRAP_PACKAGES 处理.
        两者不应出现在 [tool.auto-mas.plugin-bootstrap].packages 中, 否则会出现
        路径冲突 (前端代码会重复安装 / 版本声明被覆盖).
        """
        if not self.pyproject_path.exists():
            self.skipTest("pyproject.toml 不存在")
        declared = self._parse_bootstrap_packages()
        declared_names = {_normalize_dist_name(name) for name, _ in declared}

        for plugin_name in SYSTEM_OR_WORKSPACE_PLUGIN_NAMES:
            expected_dist = next(
                dist for name, dist, _, _ in EXPECTED_BOOTSTRAP_PLUGINS
                if name == plugin_name
            )
            normalized = _normalize_dist_name(expected_dist)
            self.assertNotIn(
                normalized,
                declared_names,
                f"系统/workspace 包 {expected_dist} 不应在 bootstrap packages 中声明 "
                f"(应走 SYSTEM_BOOTSTRAP_PACKAGES 或 dependency-groups.plugins 路径)",
            )

    def test_pyproject_does_not_declare_aggregate_packages_only(self) -> None:
        """聚合包 (automas-hsr, automas-m9a) 无 entry point, 不应作为唯一声明。"""
        if not self.pyproject_path.exists():
            self.skipTest("pyproject.toml 不存在")
        declared = self._parse_bootstrap_packages()
        declared_names = {_normalize_dist_name(name) for name, _ in declared}

        # 必须同时声明有 entry point 的 distribution, 不能只声明聚合包
        self.assertIn(
            "automas_script_hsr",
            declared_names,
            "bootstrap 必须声明 automas-script-hsr (有 entry point), 不能只用 automas-hsr 聚合包",
        )
        self.assertIn(
            "automas_script_maafw_pack_m9a",
            declared_names,
            "bootstrap 必须声明 automas-script-maafw-pack-m9a (有 entry point), 不能只用 automas-m9a 聚合包",
        )


if __name__ == "__main__":
    unittest.main()
