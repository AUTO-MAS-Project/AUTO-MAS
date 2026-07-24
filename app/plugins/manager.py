#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
import asyncio
import hashlib
import inspect
import json
import os
import re
import importlib.metadata as importlib_metadata
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict
import uuid

from app.utils import get_logger

from .event_bus import EventBus
from .config_store import PluginConfigStore
from .loader import PluginLoader
from .realtime import schedule_plugin_snapshot
from .service_registry import ServiceRegistry
from .system import (
    get_system_plugin_default_instances,
    is_system_plugin,
    is_system_plugin_package,
)
from .uv_backend import uv_pip_install, uv_pip_install_with_mirror_fallback, uv_pip_uninstall
from .pypi_site import (
    ENTRY_POINT_GROUPS,
    get_installed_plugin_entry_points,
    get_pypi_site_packages_dir,
    invalidate_entry_points_cache,
)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


logger = get_logger("插件管理器")


@dataclass
class _LocalPluginProject:
    """本地插件工程元信息。"""

    project_dir: Path
    distribution_name: str
    entry_point_names: set[str]


@dataclass(frozen=True)
class _BundledPluginLock:
    """Verified plugin distributions protected by a bundled runtime lock."""

    versions: dict[str, str]
    protected_host_distributions: frozenset[str]


@dataclass(frozen=True)
class _DeclaredScriptTypeBinding:
    """插件声明的脚本类型绑定。"""

    type_key: str
    display_name: str
    legacy_config_class: type


class _PluginManager:
    """协调插件的生命周期并为 MAS 核心提供事件 API。"""

    def __init__(self) -> None:
        self.started = False
        self.events = EventBus()
        self.config_store = PluginConfigStore()
        self.plugins_dir = Path.cwd() / "plugins"
        self.service = ServiceRegistry()
        self.runtime: Dict[str, Any] = {
            "list_scripts": self._list_scripts,
            "get_script_log": self._get_script_log,
        }
        self.loader = PluginLoader(
            events=self.events,
            runtime=self.runtime,
            plugins_dir=self.plugins_dir,
            service=self.service,
        )
        self._discover_cache: Dict[str, Any] | None = None
        self._discover_cache_time = 0.0
        self._discover_cache_plugins_dir: Path | None = None
        self._discover_cache_ttl = 30.0
        self._discover_lock = asyncio.Lock()
        self._config_write_lock = asyncio.Lock()
        # 所有会改变插件包、实例运行态或 enabled 状态的用户操作串行执行。
        # API、旧 WS、主 WS 与开发 HMR 均可触发这些入口，不能只依赖传输层锁。
        self._operation_lock = asyncio.Lock()
        self._pending_local_install: asyncio.Task | None = None

    def invalidate_discover_cache(self) -> None:
        self._discover_cache = None
        self._discover_cache_time = 0.0
        self._discover_cache_plugins_dir = None
        invalidate_entry_points_cache()

    def is_system_plugin(self, plugin_name: str) -> bool:
        return is_system_plugin(plugin_name)

    def is_system_plugin_package(self, package_name: str) -> bool:
        return is_system_plugin_package(package_name)

    def _discover_plugins(self) -> Dict[str, Any]:
        """发现插件（统一基于 Entry Point）。"""
        return self.loader.discover()

    def _iter_local_pyproject_paths(self) -> list[Path]:
        """枚举本地插件目录中的 pyproject.toml 文件。

        支持两级深度扫描：
        - 一级：plugins/<name>/pyproject.toml
        - 二级：plugins/<group>/<name>/pyproject.toml

        若一级目录自身包含 pyproject.toml 则不再深入该目录。

        Returns:
            list[Path]: 所有候选 pyproject.toml 的路径列表。

        Raises:
            OSError: 读取插件目录失败时抛出。
        """
        if not self.plugins_dir.exists():
            return []

        result: list[Path] = []
        for item in sorted(self.plugins_dir.iterdir()):
            if not item.is_dir() or item.name == "pypi" or item.name.startswith("_"):
                continue
            pyproject_path = item / "pyproject.toml"
            if pyproject_path.exists():
                result.append(pyproject_path)
                continue
            for sub_item in sorted(item.iterdir()):
                if not sub_item.is_dir() or sub_item.name.startswith("_"):
                    continue
                sub_pyproject = sub_item / "pyproject.toml"
                if sub_pyproject.exists():
                    result.append(sub_pyproject)
        return result

    def _parse_local_plugin_project(self, pyproject_path: Path) -> _LocalPluginProject | None:
        """解析本地 pyproject 并提取插件入口点信息。

        Args:
            pyproject_path (Path): pyproject.toml 文件路径。

        Returns:
            _LocalPluginProject | None: 解析成功返回工程信息；未声明插件入口点时返回 None。

        Raises:
            ValueError: 在以下场景抛出：
                1) pyproject 顶层结构非法；
                2) project 表或 entry-points 表结构非法。
            TOMLDecodeError: pyproject.toml 格式错误时抛出。
            OSError: 文件读取失败时抛出。
        """
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"pyproject 顶层必须是对象: {pyproject_path}")

        project_table = data.get("project", {})
        if not isinstance(project_table, dict):
            raise ValueError(f"pyproject project 字段必须是对象: {pyproject_path}")

        distribution_name = str(project_table.get("name") or pyproject_path.parent.name).strip()
        entry_points_table = project_table.get("entry-points", {})
        if not isinstance(entry_points_table, dict):
            raise ValueError(f"pyproject project.entry-points 必须是对象: {pyproject_path}")

        entry_point_names: set[str] = set()
        for group in ENTRY_POINT_GROUPS:
            group_table = entry_points_table.get(group)
            if not isinstance(group_table, dict):
                continue
            for ep_name in group_table.keys():
                name = str(ep_name or "").strip()
                if name:
                    entry_point_names.add(name)

        if not entry_point_names:
            return None

        return _LocalPluginProject(
            project_dir=pyproject_path.parent.resolve(),
            distribution_name=distribution_name,
            entry_point_names=entry_point_names,
        )

    def _collect_local_plugin_projects(self) -> list[_LocalPluginProject]:
        """扫描并收集本地可安装插件工程。

        Returns:
            list[_LocalPluginProject]: 可用于 editable 安装的本地工程列表。
        """
        result: list[_LocalPluginProject] = []
        for pyproject_path in self._iter_local_pyproject_paths():
            try:
                parsed = self._parse_local_plugin_project(pyproject_path)
            except Exception as e:
                logger.warning(f"解析本地插件 pyproject 失败，已跳过: path={pyproject_path}, error={type(e).__name__}: {e}")
                continue

            if parsed is None:
                logger.warning(f"本地插件未声明入口点组 {ENTRY_POINT_GROUPS}，已跳过自动安装: {pyproject_path.parent}")
                continue
            result.append(parsed)
        return result

    def _is_development_source_checkout(self) -> bool:
        """Keep editable installs enabled for an explicitly marked/source checkout."""
        if str(os.getenv("AUTO_MAS_DEV", "")).strip().lower() in {"1", "true", "yes", "on"}:
            return True
        if os.getenv("AUTO_MAS_BACKEND_OWNER_TOKEN"):
            return False
        app_root = self.plugins_dir.parent
        return (app_root / ".git").exists() and (app_root / "frontend" / "package.json").is_file()

    def _load_bundled_plugin_lock(self) -> _BundledPluginLock | None:
        """Load the release plugin set, failing closed when its integrity contract is broken."""
        app_root = self.plugins_dir.parent
        marker_path = app_root / "res" / "integration-snapshot.json"
        if not marker_path.is_file() or self._is_development_source_checkout():
            return None

        manifest_path = self.plugins_dir / "wheels" / "manifest.json"
        runtime_lock_path = self.plugins_dir / "wheels" / "runtime-lock.json"
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8-sig"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"随包插件锁标记或 manifest 无法读取，拒绝 editable 覆盖: {exc}") from exc

        contract = marker.get("wheelhouse_contract")
        runtime_lock_record = manifest.get("runtime_lock")
        expected_count = (
            contract.get("plugin_distribution_count") if isinstance(contract, dict) else None
        )
        if (
            marker.get("schema_version") != 1
            or marker.get("deployment_mode") != "bundled-snapshot"
            or manifest.get("schema_version") != 3
            or manifest.get("artifact_scope") != "complete-windows-x64-runtime-wheelhouse"
            or not isinstance(expected_count, int)
            or expected_count <= 0
            or not isinstance(runtime_lock_record, dict)
            or runtime_lock_record.get("filename") != "runtime-lock.json"
        ):
            raise RuntimeError("随包插件锁契约无效，拒绝 editable 覆盖")

        try:
            runtime_lock_bytes = runtime_lock_path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"随包 runtime-lock 缺失，拒绝 editable 覆盖: {exc}") from exc
        expected_size = runtime_lock_record.get("size_bytes")
        expected_hash = runtime_lock_record.get("sha256")
        actual_hash = hashlib.sha256(runtime_lock_bytes).hexdigest()
        if (
            not isinstance(expected_size, int)
            or expected_size != len(runtime_lock_bytes)
            or not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash)
            or actual_hash != expected_hash.lower()
        ):
            raise RuntimeError("随包 runtime-lock 与 manifest 的大小或 SHA-256 不一致，拒绝 editable 覆盖")

        try:
            runtime_lock = json.loads(runtime_lock_bytes.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(f"随包 runtime-lock 不是有效 JSON，拒绝 editable 覆盖: {exc}") from exc
        plugins = runtime_lock.get("plugins")
        host_runtime = runtime_lock.get("host_runtime")
        install_contract = runtime_lock.get("install_contract")
        if (
            runtime_lock.get("schema_version") != 1
            or not isinstance(plugins, list)
            or not isinstance(host_runtime, list)
            or not isinstance(install_contract, dict)
            or not isinstance(install_contract.get("protected_host_distributions"), list)
        ):
            raise RuntimeError("随包 runtime-lock schema 无效，拒绝 editable 覆盖")

        versions: dict[str, str] = {}
        for entry in plugins:
            if not isinstance(entry, dict) or entry.get("scope") != "plugin":
                raise RuntimeError("随包 runtime-lock 含无效 plugin scope，拒绝 editable 覆盖")
            distribution = self._normalize_distribution_name(entry.get("distribution"))
            version = str(entry.get("version") or "").strip()
            if not distribution or not version or distribution in versions:
                raise RuntimeError("随包 runtime-lock 含空值或重复插件分发，拒绝 editable 覆盖")
            versions[distribution] = version
        if len(versions) != expected_count:
            raise RuntimeError(
                f"随包 runtime-lock 插件数量不符合快照契约: expected={expected_count}, actual={len(versions)}"
            )
        host_distributions = {
            self._normalize_distribution_name(entry.get("distribution"))
            for entry in host_runtime
            if isinstance(entry, dict) and entry.get("scope") == "host_runtime"
        }
        protected_host_distributions = {
            self._normalize_distribution_name(item)
            for item in install_contract["protected_host_distributions"]
            if isinstance(item, str) and item.strip()
        }
        if (
            len(host_distributions) != len(host_runtime)
            or host_distributions != protected_host_distributions
        ):
            raise RuntimeError("随包 runtime-lock 的 protected host 集合无效，拒绝 editable 覆盖")
        return _BundledPluginLock(
            versions=versions,
            protected_host_distributions=frozenset(protected_host_distributions),
        )

    def _assert_protected_host_not_shadowed(self, bundled_lock: _BundledPluginLock) -> None:
        """The plugin target must never shadow a protected host distribution."""
        target_dir = get_pypi_site_packages_dir(self.plugins_dir)
        if not target_dir.is_dir():
            return
        shadowed = sorted(
            {
                self._normalize_distribution_name(str(getattr(dist, "name", "") or ""))
                for dist in importlib_metadata.distributions(path=[str(target_dir)])
            }
            & bundled_lock.protected_host_distributions
        )
        if shadowed:
            raise RuntimeError(
                "插件 site-packages 覆盖了受保护宿主依赖，拒绝继续启动: "
                + ", ".join(shadowed)
            )

    def _assert_locked_projects_unchanged(
        self,
        projects: list[_LocalPluginProject],
        bundled_lock: _BundledPluginLock,
    ) -> None:
        """Reject an editable/version override of a source project protected by the lock."""
        installed_entry_points = get_installed_plugin_entry_points(self.plugins_dir)
        for project in projects:
            distribution = self._normalize_distribution_name(project.distribution_name)
            expected_version = bundled_lock.versions.get(distribution)
            if expected_version is None:
                continue
            for entry_name in project.entry_point_names:
                infos = installed_entry_points.get(entry_name, [])
                valid = len(infos) == 1 and all(
                    self._normalize_distribution_name(getattr(info, "distribution", "")) == distribution
                    and str(getattr(info, "version", "") or "").strip() == expected_version
                    and getattr(info, "editable_project_path", None) is None
                    for info in infos
                )
                if not valid:
                    raise RuntimeError(
                        "锁定插件已被 editable/版本漂移覆盖，拒绝继续启动: "
                        f"distribution={project.distribution_name}, entry_point={entry_name}"
                    )

    def _should_install_local_project(
        self,
        project: _LocalPluginProject,
        installed_entry_points: Dict[str, list[Any]],
    ) -> tuple[bool, str]:
        """判定本地插件工程是否需要执行 editable 安装。

        Args:
            project (_LocalPluginProject): 本地插件工程信息。
            installed_entry_points (Dict[str, list[Any]]): 已安装入口点快照。

        Returns:
            tuple[bool, str]: (是否需要安装, 原因描述)。
        """
        expected_source = project.project_dir.resolve()
        for entry_name in sorted(project.entry_point_names):
            installed_infos = installed_entry_points.get(entry_name, [])
            if not installed_infos:
                return True, f"入口点未安装: {entry_name}"

            same_source = any(
                getattr(item, "editable_project_path", None) is not None
                and Path(getattr(item, "editable_project_path")).resolve() == expected_source
                for item in installed_infos
            )
            if not same_source:
                return True, f"入口点来源冲突，本地优先覆盖: {entry_name}"

        return False, "已安装且来源一致"

    async def _install_local_project_editable(self, project: _LocalPluginProject, reason: str) -> None:
        """将本地插件工程以 editable 方式安装到插件 site-packages。

        Args:
            project (_LocalPluginProject): 目标本地插件工程。
            reason (str): 安装触发原因。

        Returns:
            None: 无返回值。

        Raises:
            RuntimeError: 安装失败时抛出。
        """
        target_dir = get_pypi_site_packages_dir(self.plugins_dir)
        try:
            await uv_pip_install(
                [str(project.project_dir)],
                target=target_dir,
                editable=True,
            )
        except RuntimeError as e:
            raise RuntimeError(
                f"本地插件 editable 安装失败: project={project.project_dir}, reason={reason}, detail={e}"
            ) from e

        invalidate_entry_points_cache()
        logger.info(
            f"本地插件 editable 安装完成: project={project.project_dir}, distribution={project.distribution_name}, reason={reason}"
        )

    async def _ensure_local_projects_installed(self) -> None:
        """扫描本地 pyproject 并按需执行 editable 安装。

        安装策略：
        - 若入口点未安装，则自动安装；
        - 若入口点已存在但并非来自当前本地工程，则执行本地优先覆盖安装；
        - 若入口点已安装且来源一致，则跳过。

        Returns:
            None: 无返回值。

        Raises:
            RuntimeError: 任意本地插件安装失败时抛出。
        """
        projects = self._collect_local_plugin_projects()
        if not projects:
            return

        bundled_lock = self._load_bundled_plugin_lock()
        if bundled_lock is not None:
            self._assert_locked_projects_unchanged(projects, bundled_lock)
            self._assert_protected_host_not_shadowed(bundled_lock)

        installed_entry_points = get_installed_plugin_entry_points(self.plugins_dir)
        for project in projects:
            normalized_distribution = self._normalize_distribution_name(project.distribution_name)
            if bundled_lock is not None and normalized_distribution in bundled_lock.versions:
                logger.info(
                    "随包锁定插件保留 wheel 安装，跳过 editable 覆盖: "
                    f"distribution={project.distribution_name}, path={project.project_dir}"
                )
                continue
            needs_install, reason = self._should_install_local_project(project, installed_entry_points)
            if not needs_install:
                continue
            await self._install_local_project_editable(project, reason)
            installed_entry_points = get_installed_plugin_entry_points(self.plugins_dir)
        if bundled_lock is not None:
            self._assert_locked_projects_unchanged(projects, bundled_lock)
            self._assert_protected_host_not_shadowed(bundled_lock)

    def _get_valid_discover_cache(self) -> Dict[str, Any] | None:
        if self._discover_cache is None:
            return None
        if self._discover_cache_plugins_dir != self.plugins_dir:
            return None
        if time.monotonic() - self._discover_cache_time >= self._discover_cache_ttl:
            return None
        return self._discover_cache

    async def discover_plugins(self, *, force: bool = False, fast_startup: bool = False) -> Dict[str, Any]:
        """执行本地插件自动安装后再统一发现插件。

        Args:
            force: 强制刷新缓存。
            fast_startup: 为 True 时将本地插件安装放入后台，不阻塞发现流程。

        Returns:
            Dict[str, Any]: 已发现插件映射。

        Raises:
            RuntimeError: 本地插件安装失败时抛出。
        """
        if not force:
            cached = self._get_valid_discover_cache()
            if cached is not None:
                self.loader.discovered_plugins = cached
                return cached

        async with self._discover_lock:
            if not force:
                cached = self._get_valid_discover_cache()
                if cached is not None:
                    self.loader.discovered_plugins = cached
                    return cached

            if fast_startup:
                self._pending_local_install = asyncio.create_task(
                    self._ensure_local_projects_installed()
                )
            else:
                await self._ensure_local_projects_installed()
            discovered = self._discover_plugins()
            await self._ensure_default_instances(discovered)
            self.loader.discovered_plugins = discovered
            self._discover_cache = discovered
            self._discover_cache_time = time.monotonic()
            self._discover_cache_plugins_dir = self.plugins_dir
            return discovered

    async def _ensure_default_instances(self, discovered: Dict[str, Any]) -> None:
        """按插件声明补齐默认实例。"""

        default_instances: Dict[str, Dict[str, Any]] = {
            plugin_name: spec
            for plugin_name, spec in get_system_plugin_default_instances().items()
            if plugin_name in discovered
        }
        for plugin_name, plugin_source in discovered.items():
            spec = self.loader.get_default_instance_spec(plugin_name, plugin_source)
            if spec is None:
                continue
            if is_system_plugin(plugin_name):
                default_instances.setdefault(plugin_name, {}).update(spec)
                default_instances[plugin_name]["enabled"] = True
                default_instances[plugin_name]["system"] = True
                default_instances[plugin_name]["locked"] = True
            else:
                default_instances[plugin_name] = spec

        if not default_instances:
            return

        await self.config_store.ensure_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
            default_instances=default_instances,
        )

    @staticmethod
    def _normalize_distribution_name(name: str) -> str:
        """将分发名归一化为便于比较的格式。"""
        return re.sub(r"[-_.]+", "_", str(name or "").strip().lower())

    def _validate_package_name(self, package_name: str) -> str:
        """校验并规范化包名输入。

        Args:
            package_name (str): 用户输入的包名。

        Returns:
            str: 去除首尾空白后的包名。

        Raises:
            ValueError: 在以下场景抛出：
                1) 包名为空字符串；
                2) 包名包含空格字符；
                3) 包名包含非法字符（仅允许字母、数字、下划线、连字符、点号）。
        """
        normalized = str(package_name or "").strip()
        if not normalized:
            raise ValueError("包名不能为空")

        if any(ch.isspace() for ch in normalized):
            raise ValueError("包名不能包含空格")

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
        if any(ch not in allowed for ch in normalized):
            raise ValueError("包名包含非法字符，仅允许字母、数字、下划线、连字符与点号")

        return normalized

    def _iter_target_distributions(self, target_dir: Path) -> list[importlib_metadata.Distribution]:
        """枚举插件目标目录中的分发记录。"""
        if not target_dir.exists():
            return []
        return list(importlib_metadata.distributions(path=[str(target_dir)]))

    def _cleanup_package_from_target(self, package_name: str, target_dir: Path) -> bool:
        """从目标 site-packages 清理指定 distribution 记录的文件。

        Args:
            package_name (str): 分发包名。
            target_dir (Path): 目标 site-packages 目录。

        Returns:
            bool: 存在匹配并执行清理时返回 True；未发现匹配分发时返回 False。

        Raises:
            OSError: 删除文件或目录失败时抛出。
            RuntimeError: distribution RECORD 指向目标目录之外时抛出。
        """
        normalized = self._normalize_distribution_name(package_name)
        target_root = target_dir.resolve()
        matched: list[importlib_metadata.Distribution] = []

        for dist in self._iter_target_distributions(target_dir):
            dist_name = str(getattr(dist, "name", "") or "")
            if self._normalize_distribution_name(dist_name) != normalized:
                continue
            matched.append(dist)

        if not matched:
            return False

        for dist in matched:
            dist_files = list(getattr(dist, "files", []) or [])
            parent_dirs: set[Path] = set()
            for item in dist_files:
                candidate = Path(str(dist.locate_file(item)))
                resolved_candidate = candidate.resolve()
                try:
                    resolved_candidate.relative_to(target_root)
                except ValueError as exc:
                    raise RuntimeError(
                        "拒绝清理指向插件 site-packages 之外的 distribution 文件: "
                        f"package={package_name}, path={resolved_candidate}"
                    ) from exc
                if resolved_candidate == target_root:
                    raise RuntimeError(
                        f"拒绝清理插件 site-packages 根目录: package={package_name}"
                    )

                if candidate.is_symlink() or candidate.is_file():
                    candidate.unlink(missing_ok=True)
                elif candidate.is_dir():
                    try:
                        candidate.rmdir()
                    except OSError:
                        pass
                parent_dirs.add(candidate.parent)

            # 只删除已经为空的父目录，保留 namespace 包中其他 distribution 的文件。
            for directory in sorted(
                parent_dirs,
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                current = directory
                while current != target_root:
                    try:
                        current.rmdir()
                    except OSError:
                        break
                    current = current.parent

            dist_name = self._normalize_distribution_name(str(getattr(dist, "name", "") or ""))
            version = str(getattr(dist, "version", "") or "").strip()
            if dist_name and version:
                editable_pth = target_dir / f"__editable__.{dist_name}-{version}.pth"
                editable_pth.unlink(missing_ok=True)

        return True

    async def _rollback_plugin_install(
        self,
        package_name: str,
        target_dir: Path,
    ) -> tuple[bool, str]:
        """尽力回滚已安装但未通过入口验证的 distribution。"""
        details: list[str] = []
        removed_from_target = False
        try:
            removed_from_target = self._cleanup_package_from_target(
                package_name,
                target_dir,
            )
            details.append(f"removed_from_target={removed_from_target}")
        except Exception as exc:
            details.append(f"target_cleanup={type(exc).__name__}: {exc}")

        uninstall_ok = False
        try:
            completed = await uv_pip_uninstall(package_name, target=target_dir)
            uninstall_ok = completed.returncode == 0
            if not uninstall_ok:
                detail = (completed.stderr or completed.stdout or "未知错误").strip()
                details.append(f"uv_uninstall={detail}")
            else:
                details.append("uv_uninstall=ok")
        except Exception as exc:
            details.append(f"uv_uninstall={type(exc).__name__}: {exc}")

        self.invalidate_discover_cache()
        return removed_from_target or uninstall_ok, "; ".join(details)

    async def install_plugin_package(self, package_name: str) -> None:
        """串行安装一个插件 distribution。"""
        async with self._operation_lock:
            await self._finish_background_install()
            await self._install_plugin_package(package_name)

    async def _install_plugin_package(self, package_name: str) -> None:
        """从 PyPI 安装插件包到插件专用 site-packages。

        Args:
            package_name (str): PyPI 包名，例如 auto-mas-test。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 包名非法或为系统插件包时抛出。
            RuntimeError: 在以下场景抛出：
                1) 安装命令执行失败；
                2) 安装后未发现任何插件入口点（此时会回滚已安装的文件，避免幽灵 distribution）。
        """
        normalized = self._validate_package_name(package_name)
        if self.is_system_plugin_package(normalized):
            raise ValueError(f"系统插件包不可安装: {package_name}")

        target_dir = get_pypi_site_packages_dir(self.plugins_dir)
        normalized_dist = self._normalize_distribution_name(normalized)

        try:
            await uv_pip_install_with_mirror_fallback([normalized], target=target_dir)
        except RuntimeError as e:
            raise RuntimeError(f"安装插件包失败: package={normalized}, detail={e}") from e

        try:
            self.invalidate_discover_cache()
            discovered = await self.discover_plugins(force=True)

            contributed = any(
                self._normalize_distribution_name(
                    str(getattr(plugin_source, "distribution", "") or "")
                )
                == normalized_dist
                for plugin_source in discovered.values()
            )
            if not contributed:
                raise RuntimeError(
                    f"安装完成但未发现该 distribution 的插件入口点，请确认包声明了 {ENTRY_POINT_GROUPS}"
                )
        except Exception as validation_error:
            rollback_ok, rollback_detail = await self._rollback_plugin_install(
                normalized,
                target_dir,
            )
            logger.warning(
                "插件包安装后验证失败: "
                f"package={normalized}, rollback_ok={rollback_ok}, detail={rollback_detail}"
            )
            rollback_status = "回滚完成" if rollback_ok else "回滚不完整，需人工清理"
            raise RuntimeError(
                f"插件包安装后验证失败: package={normalized}, "
                f"reason={type(validation_error).__name__}: {validation_error}; "
                f"{rollback_status}: {rollback_detail}"
            ) from validation_error

        logger.info(f"插件包安装完成: package={normalized}")

    async def uninstall_plugin_package(self, package_name: str) -> None:
        """串行卸载一个插件 distribution。"""
        async with self._operation_lock:
            await self._finish_background_install()
            await self._uninstall_plugin_package(package_name)

    async def _uninstall_plugin_package(self, package_name: str) -> None:
        """卸载插件包并清理插件专用 site-packages 中的残留文件。

        Args:
            package_name (str): PyPI 包名。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 包名非法时抛出。
            RuntimeError: 当未找到可卸载分发且 uv pip uninstall 同样失败时抛出。
            OSError: 删除目标目录文件失败时抛出。
        """
        normalized = self._validate_package_name(package_name)
        if self.is_system_plugin_package(normalized):
            raise ValueError(f"系统插件包不可卸载: {package_name}")
        normalized_dist = self._normalize_distribution_name(normalized)
        target_dir = get_pypi_site_packages_dir(self.plugins_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        # 卸载前捕获被卸载包贡献的插件名集合，用于后续清理 orphan 实例。
        before_discovered = await self.discover_plugins(force=True)
        affected_plugin_names: set[str] = set()
        for plugin_name, plugin_source in before_discovered.items():
            dist_name = str(getattr(plugin_source, "distribution", "") or "")
            if self._normalize_distribution_name(dist_name) == normalized_dist:
                affected_plugin_names.add(plugin_name)

        removed_from_target = self._cleanup_package_from_target(normalized, target_dir)

        completed = await uv_pip_uninstall(normalized, target=target_dir)
        uv_ok = completed.returncode == 0

        if not removed_from_target and not uv_ok:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "未知错误"
            raise RuntimeError(f"卸载插件包失败: package={normalized}, detail={detail}")

        self.invalidate_discover_cache()
        after_discovered = await self.discover_plugins(force=True)

        # 清理 orphan 实例：被卸载包贡献且卸载后不再被发现的插件，其运行时实例和
        # 持久化配置条目都需要移除，避免留下引用已删除 distribution 的幽灵实例。
        orphan_plugin_names = {
            name for name in affected_plugin_names if name not in after_discovered
        }
        if orphan_plugin_names:
            await self._cleanup_orphan_instances(orphan_plugin_names, after_discovered)

        logger.info(f"插件包卸载完成: package={normalized}, removed_from_target={removed_from_target}")

    async def _cleanup_orphan_instances(
        self,
        orphan_plugin_names: set[str],
        discovered: Dict[str, Any],
    ) -> None:
        """清理引用已卸载插件的 orphan 实例。

        先卸载运行时实例，再从持久化配置中移除对应条目。

        Args:
            orphan_plugin_names (set[str]): 已不再被发现的插件名集合。
            discovered (Dict[str, Any]): 当前已发现插件映射，用于 get_root。
        """
        if not orphan_plugin_names:
            return

        # 1. 卸载运行时实例
        for plugin_name in list(orphan_plugin_names):
            for instance_id, record in list(self.loader.records.items()):
                if record.plugin_name == plugin_name:
                    try:
                        await self.loader.unload_instance(
                            instance_id, stop_reason="uninstall_orphan"
                        )
                    except Exception as e:
                        logger.warning(
                            f"卸载 orphan 实例失败: instance={instance_id}, "
                            f"plugin={plugin_name}, error={type(e).__name__}: {e}"
                        )
                    finally:
                        # distribution 已被移除，不能继续保留指向旧模块对象的记录。
                        self.loader.records.pop(instance_id, None)

        # 2. 从持久化配置中移除 orphan 实例条目（加锁防止与其他配置写操作交叉）
        async with self._config_write_lock:
            try:
                root = await self.config_store.get_root(
                    self.plugins_dir,
                    discovered,
                    auto_create_missing=False,
                )
            except Exception as e:
                raise RuntimeError(
                    "distribution 已卸载，但读取插件配置失败，orphan 配置尚未清理: "
                    f"{type(e).__name__}: {e}"
                ) from e

            instances = root.get("instances", [])
            if not isinstance(instances, list):
                raise RuntimeError(
                    "distribution 已卸载，但插件配置 instances 不是列表，"
                    "orphan 配置尚未清理"
                )

            original_count = len(instances)
            filtered = [
                item
                for item in instances
                if not (
                    isinstance(item, dict)
                    and str(item.get("plugin") or "") in orphan_plugin_names
                )
            ]
            removed_count = original_count - len(filtered)
            if removed_count == 0:
                return

            root["instances"] = filtered
            try:
                await self.config_store.save_root(self.plugins_dir, root)
                logger.info(
                    f"已清理 orphan 实例配置: removed={removed_count}, plugins={sorted(orphan_plugin_names)}"
                )
            except Exception as e:
                raise RuntimeError(
                    "distribution 已卸载，但保存插件配置失败，orphan 清理未落盘: "
                    f"{type(e).__name__}: {e}"
                ) from e

        schedule_plugin_snapshot(
            reason="manager.cleanup_orphan_instances",
            discovered=discovered,
        )

    async def _update_pypi_plugin(
        self,
        plugin_name: str,
        discovered: Dict[str, Any],
        update_source: str = "directory",
    ) -> None:
        """重载前更新 PyPI 插件包。

        当前策略：
        - 当插件来源为 pypi 时，优先从 plugins/<plugin_name> 本地目录执行安装更新。
        - 若本地目录不存在，则跳过并保留现有包版本。

        预留策略：
        - update_source="pip-index" 为未来在线源更新入口（当前仅记录日志）。
        """
        if self.is_system_plugin(plugin_name):
            return

        plugin_source = discovered.get(plugin_name)
        if plugin_source is None or getattr(plugin_source, "source", "") != "pypi":
            return

        if update_source == "pip-index":
            logger.info(f"预留更新策略（待实现）: plugin={plugin_name}, source=pip-index")
            return

        package_dir = self.plugins_dir / plugin_name
        pyproject_path = package_dir / "pyproject.toml"
        if not package_dir.exists() or not pyproject_path.exists():
            logger.info(
                f"PyPI 插件未找到本地包目录，跳过目录更新: plugin={plugin_name}, path={package_dir}"
            )
            return

        logger.info(
            f"PyPI plugin has a local project; skip implicit directory update to avoid replacing editable install: plugin={plugin_name}, path={package_dir}"
        )
        return

    async def _update_all_pypi_plugins(self, discovered: Dict[str, Any]) -> None:
        """批量更新已发现的 PyPI 插件。"""
        for plugin_name, plugin_source in discovered.items():
            if getattr(plugin_source, "source", "") != "pypi":
                continue
            if self.is_system_plugin(plugin_name):
                continue
            await self._update_pypi_plugin(plugin_name, discovered)

    def _list_scripts(self) -> list[Dict[str, Any]]:
        try:
            from app.core import Config
            scripts = []
            for script_id, script in Config.ScriptConfig.items():
                scripts.append(
                    {
                        "id": str(script_id),
                        "name": script.get("Info", "Name"),
                        "type": type(script).__name__,
                    }
                )
            return scripts
        except Exception as e:
            logger.warning(f"获取脚本列表失败: {e}")
            return []

    def _get_script_log(self, script_id: str, limit: int = 200) -> str:
        try:
            from app.core import Config

            uid = uuid.UUID(script_id)
            if uid not in Config.ScriptConfig:
                return ""
            script = Config.ScriptConfig[uid]

            log_value = getattr(script, "log", None)
            if isinstance(log_value, str):
                if limit <= 0:
                    return log_value
                lines = log_value.splitlines()
                return "\n".join(lines[-limit:])
            return ""
        except Exception as e:
            logger.warning(f"获取脚本日志失败: script_id={script_id}, error={e}")
            return ""

    async def _set_instance_enabled(
        self,
        instance_id: str,
        enabled: bool,
        *,
        discovered: Dict[str, Any] | None = None,
    ) -> bool:
        snapshot = discovered or await self.discover_plugins()
        if not enabled:
            instances = await self.config_store.load_instances(
                self.plugins_dir,
                snapshot,
                auto_create_missing=False,
            )
            target = next((item for item in instances if item.id == instance_id), None)
            if target is not None and self.is_system_plugin(target.plugin):
                return False

        # 使用配置写锁保护读-改-写序列，防止并发 enable/disable 请求交叉导致
        # 一方覆盖另一方的修改。
        async with self._config_write_lock:
            root = await self.config_store.get_root(
                self.plugins_dir,
                snapshot,
                auto_create_missing=False,
            )

            for item in root.get("instances", []):
                if not isinstance(item, dict):
                    continue
                if item.get("id") != instance_id:
                    continue
                if item.get("enabled") is enabled:
                    return False
                item["enabled"] = enabled
                await self.config_store.save_root(self.plugins_dir, root)
                return True

            return False

    def _collect_instance_bound_script_refs(self, instance_id: str) -> list[str]:
        """收集当前实例绑定且仍被脚本配置使用的脚本引用。"""

        from app.core import Config
        from app.core.script_types import script_type_registry
        from app.models.plugin_script_config import PluginScriptConfig

        owned_providers = [
            provider
            for provider in script_type_registry.list()
            if script_type_registry.get_owner(provider.type_key) == instance_id
        ]
        if not owned_providers:
            return []

        bound_refs: list[str] = []
        for script_id, script in Config.ScriptConfig.items():
            for provider in owned_providers:
                if isinstance(script, PluginScriptConfig):
                    type_key = str(script.get("Meta", "PluginTypeKey") or "").strip()
                    if type_key != provider.type_key:
                        continue
                    script_name = str(script.get("Info", "Name") or provider.display_name)
                    bound_refs.append(
                        f"{provider.type_key}:{script_name}({script_id})"
                    )
                    break
                if not isinstance(script, provider.script_config_class):
                    continue
                script_name = provider.display_name
                if (
                    "Info" in script._config_item_index
                    and "Name" in script._config_item_index["Info"]
                ):
                    script_name = script.get("Info", "Name")
                bound_refs.append(
                    f"{provider.type_key}:{script_name}({script_id})"
                )
                break

        return bound_refs

    async def ensure_instance_can_unload(self, instance_id: str) -> None:
        """兼容旧调用：停用实例时允许脚本进入离线只读状态。"""

        _ = instance_id

    def _collect_declared_instance_bound_script_refs(
        self,
        instance_id: str,
        *,
        plugin_name: str,
        discovered: Dict[str, Any] | None = None,
    ) -> list[str]:
        """按插件声明收集已停用实例仍占用的脚本配置。"""

        from app.core import Config
        from app.models.ConfigBase import ConfigBase
        from app.models import config as config_models
        from app.models.plugin_script_config import PluginScriptConfig

        _ = instance_id
        snapshot = discovered or self.loader.discovered_plugins or self._discover_plugins()
        plugin_source = snapshot.get(plugin_name)
        if plugin_source is None:
            return []

        try:
            module, plugin_class = self.loader._resolve_plugin_module_and_class(
                plugin_name,
                plugin_source,
                clear_cache=False,
            )
        except Exception as e:
            logger.warning(
                f"读取插件脚本类型绑定失败，已跳过: plugin={plugin_name}, error={type(e).__name__}: {e}"
            )
            return []

        raw_adapter_type_keys = (
            getattr(module, "SCRIPT_ADAPTER_TYPE_KEYS", None)
            if module is not None
            else None
        ) or getattr(plugin_class, "SCRIPT_ADAPTER_TYPE_KEYS", ())
        if not isinstance(raw_adapter_type_keys, tuple):
            raw_adapter_type_keys = ()
        adapter_type_keys = {
            str(item).strip()
            for item in raw_adapter_type_keys
            if str(item or "").strip()
        }

        raw_bindings = None
        if module is not None:
            raw_bindings = getattr(module, "SCRIPT_TYPE_BINDINGS", None)
        if raw_bindings is None:
            raw_bindings = getattr(plugin_class, "SCRIPT_TYPE_BINDINGS", None)
        if raw_bindings is None and not adapter_type_keys:
            return []
        if isinstance(raw_bindings, dict):
            raw_bindings = [raw_bindings]
        if raw_bindings is None:
            raw_bindings = []
        if not isinstance(raw_bindings, list):
            logger.warning(f"插件脚本类型绑定声明无效，已跳过: plugin={plugin_name}")
            raw_bindings = []

        bindings: list[tuple[str, str, type]] = []
        for item in raw_bindings:
            if not isinstance(item, dict):
                continue
            class_name = str(item.get("script_config_class_name") or "").strip()
            config_class = getattr(config_models, class_name, None)
            if not isinstance(config_class, type) or not issubclass(config_class, ConfigBase):
                continue
            type_key = str(item.get("type_key") or class_name).strip()
            display_name = str(item.get("display_name") or type_key).strip()
            bindings.append((type_key, display_name, config_class))

        bound_refs: list[str] = []
        for script_id, script in Config.ScriptConfig.items():
            if isinstance(script, PluginScriptConfig):
                type_key = str(script.get("Meta", "PluginTypeKey") or "").strip()
                if type_key in adapter_type_keys:
                    script_name = str(script.get("Info", "Name") or type_key)
                    bound_refs.append(f"{type_key}:{script_name}({script_id})")
                continue
            for type_key, display_name, config_class in bindings:
                if not isinstance(script, config_class):
                    continue
                script_name = display_name
                if (
                    "Info" in script._config_item_index
                    and "Name" in script._config_item_index["Info"]
                ):
                    script_name = script.get("Info", "Name")
                bound_refs.append(f"{type_key}:{script_name}({script_id})")
                break
        return bound_refs

    def _resolve_declared_script_type_bindings(
        self,
        plugin_name: str,
        *,
        discovered: Dict[str, Any] | None = None,
    ) -> list[_DeclaredScriptTypeBinding]:
        """解析插件声明的脚本类型绑定。"""

        from app.models.ConfigBase import ConfigBase
        from app.models import config as config_models

        snapshot = discovered or self.loader.discovered_plugins or self._discover_plugins()
        plugin_source = snapshot.get(plugin_name)
        if plugin_source is None:
            return []

        try:
            module, plugin_class = self.loader._resolve_plugin_module_and_class(
                plugin_name,
                plugin_source,
                clear_cache=False,
            )
        except Exception as e:
            logger.warning(
                f"读取插件脚本类型绑定失败，已跳过: plugin={plugin_name}, error={type(e).__name__}: {e}"
            )
            return []

        raw_bindings = None
        if module is not None:
            raw_bindings = getattr(module, "SCRIPT_TYPE_BINDINGS", None)
        if raw_bindings is None:
            raw_bindings = getattr(plugin_class, "SCRIPT_TYPE_BINDINGS", None)
        if raw_bindings is None:
            return []
        if isinstance(raw_bindings, dict):
            raw_bindings = [raw_bindings]
        if not isinstance(raw_bindings, list):
            logger.warning(f"插件脚本类型绑定声明无效，已跳过: plugin={plugin_name}")
            return []

        bindings: list[_DeclaredScriptTypeBinding] = []
        for item in raw_bindings:
            if not isinstance(item, dict):
                continue
            class_name = str(item.get("script_config_class_name") or "").strip()
            config_class = getattr(config_models, class_name, None)
            if not isinstance(config_class, type) or not issubclass(config_class, ConfigBase):
                continue
            type_key = str(item.get("type_key") or class_name).strip()
            if not type_key:
                continue
            display_name = str(item.get("display_name") or type_key).strip() or type_key
            bindings.append(
                _DeclaredScriptTypeBinding(
                    type_key=type_key,
                    display_name=display_name,
                    legacy_config_class=config_class,
                )
            )

        return bindings

    async def _sync_script_types_and_migrate_legacy_configs(
        self,
        *,
        discovered: Dict[str, Any] | None = None,
    ) -> None:
        """同步脚本类型映射，并把旧宿主脚本配置迁移到插件当前类。"""

        from app.core import Config
        from app.core.script_types import (
            apply_script_type_registry_to_global_config,
            script_type_registry,
        )
        from app.models.ConfigBase import ConfigBase

        apply_script_type_registry_to_global_config(Config)

        migrated_scripts: list[str] = []
        for record in self.loader.records.values():
            if getattr(record, "status", "") != "active":
                continue

            bindings = self._resolve_declared_script_type_bindings(
                record.plugin_name,
                discovered=discovered,
            )
            if not bindings:
                continue

            for binding in bindings:
                try:
                    provider = script_type_registry.get(binding.type_key)
                except KeyError:
                    continue

                if script_type_registry.get_owner(binding.type_key) != record.instance_id:
                    continue
                if not issubclass(provider.script_config_class, ConfigBase):
                    continue
                if binding.legacy_config_class is provider.script_config_class:
                    continue

                for script_id, script in list(Config.ScriptConfig.items()):
                    if type(script) is provider.script_config_class:
                        continue
                    if not isinstance(script, binding.legacy_config_class):
                        continue

                    script_name = str(script_id)
                    try:
                        if (
                            "Info" in script._config_item_index
                            and "Name" in script._config_item_index["Info"]
                        ):
                            script_name = str(script.get("Info", "Name") or script_id)
                    except Exception:
                        script_name = str(script_id)

                    try:
                        legacy_migrator = provider.metadata.get(
                            "legacy_config_migrator"
                        )
                        if callable(legacy_migrator):
                            new_script = legacy_migrator(script, provider)
                            if inspect.isawaitable(new_script):
                                new_script = await new_script
                            if not isinstance(
                                new_script,
                                provider.script_config_class,
                            ):
                                raise TypeError(
                                    "legacy_config_migrator must return "
                                    f"{provider.script_config_class.__name__}"
                                )
                        else:
                            raw_data = await script.toDict(if_decrypt=False)
                            new_script = provider.script_config_class()
                            await new_script.load(raw_data)
                        for save_method in Config.ScriptConfig._save_methods:
                            await new_script.add_save_method(save_method)
                        if Config.ScriptConfig.file:
                            await new_script.add_save_method(Config.ScriptConfig.save)
                        Config.ScriptConfig.data[script_id] = new_script
                        migrated_scripts.append(
                            f"{binding.type_key}:{script_name}({script_id})"
                        )
                    except Exception as e:
                        logger.warning(
                            "旧脚本配置自动迁移失败，将继续使用当前对象: "
                            f"plugin={record.plugin_name}, instance_id={record.instance_id}, "
                            f"type_key={binding.type_key}, script_id={script_id}, "
                            f"error={type(e).__name__}: {e}"
                        )

        if migrated_scripts:
            await Config.ScriptConfig.save()
            logger.warning(
                "检测到旧版脚本配置，已自动迁移到插件当前类型并保存: "
                + "; ".join(migrated_scripts)
            )

    async def ensure_instance_can_delete(
        self,
        instance_id: str,
        *,
        plugin_name: str | None = None,
        discovered: Dict[str, Any] | None = None,
    ) -> None:
        """校验插件实例是否允许删除。"""

        if plugin_name and self.is_system_plugin(plugin_name):
            raise RuntimeError(f"系统插件不可删除: {plugin_name}")

        bound_refs = self._collect_instance_bound_script_refs(instance_id)
        if not bound_refs and plugin_name:
            bound_refs = self._collect_declared_instance_bound_script_refs(
                instance_id,
                plugin_name=plugin_name,
                discovered=discovered,
            )
        if bound_refs:
            raise RuntimeError(
                "插件实例仍被脚本配置占用，无法删除。请先删除或迁移这些脚本: "
                + "; ".join(bound_refs)
            )

    def _select_plugins_dir(self, plugins_dir: Path | None) -> None:
        """在操作锁内切换本次事务使用的插件目录。"""

        if plugins_dir is None:
            return
        resolved = Path(plugins_dir)
        self.plugins_dir = resolved
        self.loader.plugins_dir = resolved

    @staticmethod
    def _find_instance_dict(root: Dict[str, Any], instance_id: str) -> Dict[str, Any] | None:
        for item in root.get("instances", []):
            if isinstance(item, dict) and item.get("id") == instance_id:
                return item
        return None

    @staticmethod
    def _runtime_record_error(
        record: Any,
        *,
        action: str,
        instance_id: str,
        expected_status: str,
    ) -> RuntimeError | None:
        if record is None:
            return RuntimeError(f"插件实例{action}未返回运行态记录: {instance_id}")
        status = str(getattr(record, "status", ""))
        if status == expected_status:
            return None
        detail = str(getattr(record, "error", "") or f"unexpected status={status or '<empty>'}")
        return RuntimeError(
            f"插件实例{action}失败: instance_id={instance_id}, "
            f"status={status or '<empty>'}, error={detail}"
        )

    async def _load_instance_strict(
        self,
        instance: Dict[str, Any],
        *,
        reason: str,
        reload_existing: bool,
        action: str = "加载",
    ) -> None:
        instance_id = str(instance.get("id") or "")
        plugin_name = str(instance.get("plugin") or "")
        instance_name = str(instance.get("name") or instance_id)
        config = instance.get("config", {})
        if not isinstance(config, dict):
            raise ValueError(f"插件实例配置无效: {instance_id}")

        if reload_existing:
            record = await self.loader.reload_instance(
                instance_id=instance_id,
                plugin_name=plugin_name,
                instance_name=instance_name,
                config=deepcopy(config),
                reason=reason,
            )
        else:
            record = await self.loader.load_instance(
                instance_id=instance_id,
                plugin_name=plugin_name,
                instance_name=instance_name,
                config=deepcopy(config),
            )

        error = self._runtime_record_error(
            record,
            action=action,
            instance_id=instance_id,
            expected_status="active",
        )
        if error is not None:
            raise error

    async def _reload_instance_strict(
        self,
        instance: Dict[str, Any],
        *,
        reason: str,
    ) -> None:
        """严格重载实例，失败时按原配置尝试恢复运行态。"""

        try:
            await self._load_instance_strict(
                instance,
                reason=reason,
                reload_existing=True,
                action="重载",
            )
        except Exception as reload_error:
            try:
                await self._restore_instance_runtime(
                    instance,
                    instance,
                    operation="重载",
                )
            except Exception as rollback_error:
                raise RuntimeError(
                    "插件实例重载失败且运行态恢复失败: "
                    f"{type(reload_error).__name__}: {reload_error}; "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                ) from reload_error
            raise RuntimeError(
                "插件实例重载失败，运行态已尝试恢复: "
                f"{type(reload_error).__name__}: {reload_error}"
            ) from reload_error

    async def _unload_instance_strict(self, instance_id: str, *, reason: str) -> None:
        await self.loader.unload_instance(instance_id, stop_reason=reason)
        records = getattr(self.loader, "records", {})
        record = records.get(instance_id) if isinstance(records, dict) else None
        if record is None:
            return
        error = self._runtime_record_error(
            record,
            action="卸载",
            instance_id=instance_id,
            expected_status="unloaded",
        )
        if error is not None:
            raise error

    async def _restore_instance_runtime(
        self,
        previous_instance: Dict[str, Any] | None,
        attempted_instance: Dict[str, Any],
        *,
        operation: str,
    ) -> None:
        """在持久化回滚后恢复操作前的运行态。"""

        instance_id = str(attempted_instance.get("id") or "")
        if previous_instance is None:
            await self._unload_instance_strict(
                instance_id,
                reason=f"rollback:{operation}",
            )
            return

        if bool(previous_instance.get("enabled", False)):
            await self._load_instance_strict(
                previous_instance,
                reason=f"rollback:{operation}",
                reload_existing=True,
            )
            return

        await self._unload_instance_strict(
            instance_id,
            reason=f"rollback:{operation}",
        )

    async def _raise_transaction_failure(
        self,
        *,
        operation: str,
        cause: Exception,
        previous_root: Dict[str, Any],
        previous_instance: Dict[str, Any] | None,
        attempted_instance: Dict[str, Any],
    ) -> None:
        """回滚配置和运行态，并抛出包含一致性结果的错误。"""

        rollback_errors: list[str] = []
        try:
            async with self._config_write_lock:
                await self.config_store.save_root(
                    self.plugins_dir,
                    deepcopy(previous_root),
                )
        except Exception as rollback_error:
            rollback_errors.append(
                "配置回滚失败: "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )

        try:
            await self._restore_instance_runtime(
                previous_instance,
                attempted_instance,
                operation=operation,
            )
        except Exception as rollback_error:
            rollback_errors.append(
                "运行态回滚失败: "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )

        cause_text = f"{type(cause).__name__}: {cause}"
        if rollback_errors:
            raise RuntimeError(
                f"插件实例{operation}失败且回滚不完整: {cause_text}; "
                + "; ".join(rollback_errors)
            ) from cause
        raise RuntimeError(
            f"插件实例{operation}失败，配置与运行态已回滚: {cause_text}"
        ) from cause

    async def create_instance_transaction(
        self,
        *,
        plugin_name: str,
        name: str | None,
        enabled: bool,
        config: Dict[str, Any],
        plugins_dir: Path | None = None,
    ) -> Dict[str, Any]:
        """原子新增实例：配置 RMW 与可选运行态加载共用操作锁。"""

        async with self._operation_lock:
            self._select_plugins_dir(plugins_dir)
            discovered = await self.discover_plugins()
            if plugin_name not in discovered:
                raise ValueError(f"未发现插件: {plugin_name}")
            if self.is_system_plugin(plugin_name):
                raise ValueError(f"系统插件不允许新增实例: {plugin_name}")

            effective_config = self.config_store.load_effective_config(
                plugin_name,
                config,
            )
            async with self._config_write_lock:
                root = await self.config_store.get_root(
                    self.plugins_dir,
                    discovered,
                    auto_create_missing=False,
                )
                previous_root = deepcopy(root)
                instance = {
                    "id": self.config_store.generate_instance_id(plugin_name),
                    "plugin": plugin_name,
                    "enabled": enabled,
                    "name": name or f"{plugin_name} 实例",
                    "config": effective_config,
                }
                root.setdefault("instances", []).append(instance)
                await self.config_store.save_root(self.plugins_dir, root)

            if self.started and enabled:
                try:
                    await self._load_instance_strict(
                        instance,
                        reason="manager.create_instance",
                        reload_existing=True,
                    )
                except Exception as error:
                    await self._raise_transaction_failure(
                        operation="新增",
                        cause=error,
                        previous_root=previous_root,
                        previous_instance=None,
                        attempted_instance=instance,
                    )

            return deepcopy(instance)

    async def update_instance_transaction(
        self,
        *,
        instance_id: str,
        plugin_name: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        config: Dict[str, Any] | None = None,
        plugins_dir: Path | None = None,
    ) -> Dict[str, Any]:
        """原子更新实例，并在运行态失败时恢复旧配置和旧实例。"""

        async with self._operation_lock:
            self._select_plugins_dir(plugins_dir)
            name_only = (
                name is not None
                and plugin_name is None
                and enabled is None
                and config is None
            )
            enabled_only = (
                enabled is not None
                and plugin_name is None
                and name is None
                and config is None
            )
            need_discover = plugin_name is not None or config is not None or (
                self.started and not name_only
            )
            discovered = await self.discover_plugins() if need_discover else {}

            async with self._config_write_lock:
                root = await self.config_store.get_root(
                    self.plugins_dir,
                    discovered,
                    auto_create_missing=False,
                )
                previous_root = deepcopy(root)
                target = self._find_instance_dict(root, instance_id)
                if target is None:
                    raise ValueError(f"未找到插件实例: {instance_id}")

                previous_instance = deepcopy(target)
                target_plugin = str(target.get("plugin") or "")
                if self.is_system_plugin(target_plugin):
                    if plugin_name is not None and plugin_name != target_plugin:
                        raise ValueError(f"系统插件不可变更插件类型: {target_plugin}")
                    if enabled is False:
                        raise ValueError(f"系统插件不可禁用: {target_plugin}")

                next_plugin = plugin_name if plugin_name is not None else target_plugin
                if not next_plugin:
                    raise ValueError(f"插件实例缺少有效 plugin 字段: {instance_id}")

                if plugin_name is None and config is None:
                    effective_config = target.get("config", {})
                    if not isinstance(effective_config, dict):
                        raise ValueError(f"插件实例配置无效: {instance_id}")
                    effective_config = deepcopy(effective_config)
                else:
                    if next_plugin not in discovered:
                        raise ValueError(f"未发现插件: {next_plugin}")
                    raw_config = config if config is not None else target.get("config", {})
                    effective_config = self.config_store.load_effective_config(
                        next_plugin,
                        raw_config,
                    )

                target["plugin"] = next_plugin
                target["config"] = effective_config
                if name is not None:
                    target["name"] = name
                if enabled is not None:
                    target["enabled"] = enabled
                attempted_instance = deepcopy(target)
                await self.config_store.save_root(self.plugins_dir, root)

            if self.started and not name_only:
                was_enabled = bool(previous_instance.get("enabled", False))
                is_enabled = bool(attempted_instance.get("enabled", False))
                try:
                    if enabled_only and was_enabled != is_enabled:
                        if is_enabled:
                            await self._load_instance_strict(
                                attempted_instance,
                                reason="manager.update_instance.enabled",
                                reload_existing=False,
                            )
                        else:
                            await self._unload_instance_strict(
                                instance_id,
                                reason="manager.update_instance.enabled",
                            )
                    elif is_enabled:
                        await self._load_instance_strict(
                            attempted_instance,
                            reason="manager.update_instance",
                            reload_existing=True,
                        )
                    else:
                        await self._unload_instance_strict(
                            instance_id,
                            reason="manager.update_instance",
                        )
                except Exception as error:
                    await self._raise_transaction_failure(
                        operation="更新",
                        cause=error,
                        previous_root=previous_root,
                        previous_instance=previous_instance,
                        attempted_instance=attempted_instance,
                    )

            snapshot_reason = "api.plugins.update"
            if name_only:
                snapshot_reason = "api.plugins.update.name"
            elif enabled_only:
                snapshot_reason = "api.plugins.update.enabled"
            return {
                "instance": deepcopy(attempted_instance),
                "snapshot_reason": snapshot_reason,
            }

    async def delete_instance_transaction(
        self,
        instance_id: str,
        *,
        plugins_dir: Path | None = None,
    ) -> Dict[str, Any]:
        """原子删除实例；卸载失败时恢复配置与删除前运行态。"""

        async with self._operation_lock:
            self._select_plugins_dir(plugins_dir)
            discovered = await self.discover_plugins()
            async with self._config_write_lock:
                root = await self.config_store.get_root(
                    self.plugins_dir,
                    discovered,
                    auto_create_missing=False,
                )
                previous_root = deepcopy(root)
                target = self._find_instance_dict(root, instance_id)
                if target is None:
                    raise ValueError(f"未找到插件实例: {instance_id}")
                previous_instance = deepcopy(target)
                target_plugin = str(target.get("plugin") or "")
                if self.is_system_plugin(target_plugin):
                    raise ValueError(f"系统插件不可删除: {target_plugin}")

                if self.started:
                    await self.ensure_instance_can_delete(
                        instance_id,
                        plugin_name=target_plugin,
                        discovered=discovered,
                    )

                root["instances"] = [
                    item
                    for item in root.get("instances", [])
                    if not (isinstance(item, dict) and item.get("id") == instance_id)
                ]
                await self.config_store.save_root(self.plugins_dir, root)

            if self.started:
                try:
                    await self._unload_instance_strict(
                        instance_id,
                        reason="manager.delete_instance",
                    )
                except Exception as error:
                    await self._raise_transaction_failure(
                        operation="删除",
                        cause=error,
                        previous_root=previous_root,
                        previous_instance=previous_instance,
                        attempted_instance=previous_instance,
                    )

            return previous_instance

    async def apply_instance_enabled(self, instance_id: str, enabled: bool) -> None:
        """串行应用实例启停，避免与安装、卸载或重载交叉。"""
        async with self._operation_lock:
            await self._apply_instance_enabled(instance_id, enabled)

    async def _apply_instance_enabled(self, instance_id: str, enabled: bool) -> None:
        """Apply an already-saved enabled toggle without a full instance reload."""
        discovered = await self.discover_plugins()
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        target = next((item for item in instances if item.id == instance_id), None)
        if target is None:
            raise ValueError(f"未找到插件实例: {instance_id}")

        if not enabled and target is not None and self.is_system_plugin(target.plugin):
            raise ValueError(f"系统插件不可禁用: {target.plugin}")

        if enabled:
            record = await self.loader.load_instance(
                instance_id=target.id,
                plugin_name=target.plugin,
                instance_name=target.name,
                config=target.config,
            )
            if getattr(record, "status", "") == "error":
                changed = await self._set_instance_enabled(
                    target.id,
                    False,
                    discovered=discovered,
                )
                if changed:
                    logger.warning(
                        f"插件实例启用失败，已自动禁用: instance_id={target.id}, error={record.error}"
                    )
        else:
            await self.loader.unload_instance(instance_id)

        await self._sync_script_types_and_migrate_legacy_configs(discovered=discovered)
        schedule_plugin_snapshot(
            reason="manager.apply_instance_enabled",
            discovered=discovered,
        )

    async def start(self, *, fast_startup: bool = False) -> None:
        """
        启动插件系统并按配置加载实例。

        Args:
            fast_startup: 为 True 时将本地插件安装放入后台任务，加快启动。

        Returns:
            None: 无返回值。
        """
        if self.started:
            logger.warning("插件系统已启动，忽略重复启动")
            return

        discovered = await self.discover_plugins(fast_startup=fast_startup)
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        await self.loader.load_instances(instances)
        await self._sync_script_types_and_migrate_legacy_configs(discovered=discovered)
        if not fast_startup:
            asyncio.create_task(self._repair_invalid_instances_after_start(discovered))
        self.started = True
        schedule_plugin_snapshot(reason="manager.start", discovered=discovered)
        logger.info("插件系统启动完成")

    async def _finish_background_install(self) -> None:
        """等待 fast_startup 触发的后台本地插件安装完成并刷新发现缓存。"""
        if self._pending_local_install is None:
            return
        try:
            await self._pending_local_install
        except Exception as e:
            logger.warning(f"后台本地插件安装失败: {type(e).__name__}: {e}")
        finally:
            self._pending_local_install = None
        self.invalidate_discover_cache()

    async def _repair_invalid_instances_after_start(self, discovered: Dict[str, Any]) -> None:
        """启动后修复失效插件实例配置。"""
        failed = dict(getattr(self.loader, "startup_failed_instances", {}) or {})
        if not failed:
            return

        missing_ids = set(getattr(self.loader, "startup_missing_instances", set()) or set())

        try:
            root = await self.config_store.get_root(
                self.plugins_dir,
                discovered,
                auto_create_missing=False,
            )
        except Exception as e:
            logger.error(f"读取插件配置失败，跳过失效实例修复: {type(e).__name__}: {e}")
            return

        instances = root.get("instances", [])
        if not isinstance(instances, list):
            return

        changed = False
        removed_ids: list[str] = []
        disabled_ids: list[str] = []
        new_instances = []

        for item in instances:
            if not isinstance(item, dict):
                new_instances.append(item)
                continue

            instance_id = str(item.get("id") or "")
            if not instance_id:
                new_instances.append(item)
                continue

            if instance_id in missing_ids:
                removed_ids.append(instance_id)
                changed = True
                continue

            if instance_id in failed and bool(item.get("enabled", False)):
                item["enabled"] = False
                disabled_ids.append(instance_id)
                changed = True

            new_instances.append(item)

        if not changed:
            return

        root["instances"] = new_instances
        try:
            await self.config_store.save_root(self.plugins_dir, root)
        except Exception as e:
            logger.error(f"保存插件配置失败，失效实例修复未落盘: {type(e).__name__}: {e}")
            return

        if removed_ids:
            logger.warning(f"已删除未发现插件的实例配置: {', '.join(removed_ids)}")
        if disabled_ids:
            logger.warning(f"已自动禁用启动失败的插件实例: {', '.join(disabled_ids)}")

        schedule_plugin_snapshot(
            reason="manager.repair_invalid_instances",
            discovered=discovered,
        )

    async def stop(self) -> None:
        """
        停止插件系统并卸载全部实例。

        Returns:
            None: 无返回值。
        """
        if not self.started:
            return

        # 取消 fast_startup 触发的后台本地插件安装任务，避免其在 unload_all 之后
        # 重新写入 site-packages 或触发 discover 缓存失效，导致关闭过程出现竞态。
        pending_install = self._pending_local_install
        self._pending_local_install = None
        if pending_install is not None and not pending_install.done():
            pending_install.cancel()
            try:
                await pending_install
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"停止插件系统时取消后台安装任务失败: {type(e).__name__}: {e}")

        await self.loader.unload_all()
        self.events.clear()
        self.started = False
        logger.info("插件系统已关闭")

    def on(self, event: str, handler: Callable[[Any], Any], **kwargs: Any) -> str:
        """
        注册插件系统事件监听器。

        Args:
            event (str): 事件名。
            handler: 事件处理函数。
            **kwargs (Any): 附加注册参数（priority、scope、once、error_policy 等）。

        Returns:
            str: 注册后的监听器 ID。
        """
        return self.events.on(event, handler, **kwargs)

    def off(self, event: str, handler: Callable[[Any], Any] | None = None, *, listener_id: str | None = None) -> None:
        """
        移除插件系统事件监听器。

        Args:
            event (str): 事件名。
            handler: 需要移除的事件处理函数。
            listener_id (str | None): 监听器 ID。

        Returns:
            None: 无返回值。
        """
        self.events.off(event, handler, listener_id=listener_id)

    async def emit_async(self, event: str, payload: Any = None, **kwargs: Any) -> None:
        """
        以异步方式向插件系统广播事件。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷，默认为 None。
            **kwargs (Any): 透传给事件总线的附加参数。

        Returns:
            None: 无返回值。
        """
        await self.events.emit(event, payload, **kwargs)

    def emit(self, event: str, payload: Any = None, **kwargs: Any) -> None:
        """
        同步桥接方式广播事件。

        该方法用于过渡期兼容：
        - 若存在运行中的事件循环，则创建后台任务异步发送。
        - 若不存在运行中的事件循环，则直接 `asyncio.run` 完成发送。

        Args:
            event (str): 事件名。
            payload (Any): 事件载荷，默认为 None。
            **kwargs (Any): 透传给事件总线的附加参数。

        Returns:
            None: 无返回值。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.emit_async(event, payload, **kwargs))
            return

        loop.create_task(self.emit_async(event, payload, **kwargs))

    def list_plugins(self) -> Dict[str, str]:
        """
        列出当前已加载插件实例及其状态。

        Returns:
            Dict[str, str]: 键为实例 ID，值为实例状态。
        """
        return {
            instance_id: record.status
            for instance_id, record in self.loader.records.items()
        }

    async def reload(self) -> None:
        """串行重载整个插件系统。"""
        async with self._operation_lock:
            await self._reload()

    async def _reload(self) -> None:
        """
        重载插件系统并重新加载所有可用实例。

        Returns:
            None: 无返回值。

        Raises:
            RuntimeError: 更新某个 PyPI 插件包失败时抛出（pip 安装命令返回非 0）。
            ValueError: 重启过程中读取或校验插件实例配置失败时抛出。
        """
        discovered = await self.discover_plugins()
        await self._update_all_pypi_plugins(discovered)
        if self.started:
            await self.stop()
        await self.start()
        schedule_plugin_snapshot(reason="manager.reload", discovered=discovered)

    async def reload_instance(self, instance_id: str, *, refresh_package: bool = False) -> None:
        """串行重载一个插件实例。"""
        async with self._operation_lock:
            await self._reload_instance(
                instance_id,
                refresh_package=refresh_package,
            )

    async def _reload_instance(self, instance_id: str, *, refresh_package: bool = False) -> None:
        """
        重载指定插件实例。

        Args:
            instance_id (str): 目标实例 ID。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 在以下场景抛出：
                1) 未找到目标实例；
                2) 实例配置读取后校验失败。
            RuntimeError: 目标实例对应 PyPI 插件更新失败时抛出。
        """
        discovered = await self.discover_plugins()
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        target = next((item for item in instances if item.id == instance_id), None)
        if target is None:
            raise ValueError(f"未找到插件实例: {instance_id}")

        if refresh_package:
            await self._update_pypi_plugin(target.plugin, discovered)

        instance = {
            "id": target.id,
            "plugin": target.plugin,
            "name": target.name,
            "config": deepcopy(target.config),
            "enabled": target.enabled,
        }
        try:
            if target.enabled:
                await self._reload_instance_strict(
                    instance,
                    reason="manager.reload_instance",
                )
            else:
                await self._unload_instance_strict(
                    instance_id,
                    reason="manager.reload_instance",
                )
        except Exception:
            schedule_plugin_snapshot(
                reason="manager.reload_instance_failed",
                discovered=discovered,
            )
            raise
        schedule_plugin_snapshot(
            reason="manager.reload_instance",
            discovered=discovered,
        )

    async def reload_plugin(self, plugin_name: str, *, refresh_package: bool = False) -> None:
        """串行重载一个插件的全部实例。"""
        async with self._operation_lock:
            await self._reload_plugin(
                plugin_name,
                refresh_package=refresh_package,
            )

    async def _reload_plugin(self, plugin_name: str, *, refresh_package: bool = False) -> None:
        """
        重载指定插件的全部实例。

        Args:
            plugin_name (str): 插件名。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 在以下场景抛出：
                1) 未找到该插件对应实例；
                2) 插件实例配置读取后校验失败。
            RuntimeError: 目标 PyPI 插件更新失败时抛出。
        """
        discovered = await self.discover_plugins()
        if refresh_package:
            await self._update_pypi_plugin(plugin_name, discovered)
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        matched = [item for item in instances if item.plugin == plugin_name]
        if not matched:
            raise ValueError(f"未找到插件实例: {plugin_name}")

        reload_errors: list[str] = []
        for item in matched:
            instance = {
                "id": item.id,
                "plugin": item.plugin,
                "name": item.name,
                "config": deepcopy(item.config),
                "enabled": item.enabled,
            }
            if not item.enabled:
                try:
                    await self._unload_instance_strict(
                        item.id,
                        reason="manager.reload_plugin",
                    )
                except Exception as error:
                    reload_errors.append(str(error))
                continue
            try:
                await self._reload_instance_strict(
                    instance,
                    reason="manager.reload_plugin",
                )
            except Exception as error:
                reload_errors.append(str(error))

        if reload_errors:
            logger.warning(
                f"插件重载存在失败实例: plugin={plugin_name}, errors={'; '.join(reload_errors)}"
            )
        schedule_plugin_snapshot(
            reason="manager.reload_plugin",
            discovered=discovered,
        )
        if reload_errors:
            raise RuntimeError(
                f"插件重载失败: plugin={plugin_name}; " + "; ".join(reload_errors)
            )


PluginManager = _PluginManager()
