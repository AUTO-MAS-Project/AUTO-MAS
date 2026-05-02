#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from pathlib import Path
import asyncio
import shutil
import importlib.metadata as importlib_metadata
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict
import uuid

from app.utils import get_logger

from .event_bus import EventBus
from .config_store import PluginConfigStore
from .loader import PluginLoader
from .realtime import schedule_plugin_snapshot
from .service_registry import ServiceRegistry
from .uv_backend import uv_pip_install, uv_pip_install_with_mirror_fallback, uv_pip_uninstall
from .pypi_site import ENTRY_POINT_GROUPS, get_installed_plugin_entry_points, get_pypi_site_packages_dir

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


class _PluginManager:
    """协调插件的生命周期并为 MAS 核心提供事件 API。"""

    def __init__(self) -> None:
        self.started = False
        schedule_plugin_snapshot(reason="manager.stop")
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

    def invalidate_discover_cache(self) -> None:
        self._discover_cache = None
        self._discover_cache_time = 0.0
        self._discover_cache_plugins_dir = None

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
            if not item.is_dir() or item.name == "pypi":
                continue
            pyproject_path = item / "pyproject.toml"
            if pyproject_path.exists():
                result.append(pyproject_path)
                continue
            for sub_item in sorted(item.iterdir()):
                if not sub_item.is_dir():
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

        installed_entry_points = get_installed_plugin_entry_points(self.plugins_dir)
        for project in projects:
            needs_install, reason = self._should_install_local_project(project, installed_entry_points)
            if not needs_install:
                continue
            await self._install_local_project_editable(project, reason)
            installed_entry_points = get_installed_plugin_entry_points(self.plugins_dir)

    def _get_valid_discover_cache(self) -> Dict[str, Any] | None:
        if self._discover_cache is None:
            return None
        if self._discover_cache_plugins_dir != self.plugins_dir:
            return None
        if time.monotonic() - self._discover_cache_time >= self._discover_cache_ttl:
            return None
        return self._discover_cache

    async def discover_plugins(self, *, force: bool = False) -> Dict[str, Any]:
        """执行本地插件自动安装后再统一发现插件。

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

        default_instances: Dict[str, Dict[str, Any]] = {}
        for plugin_name, plugin_source in discovered.items():
            spec = self.loader.get_default_instance_spec(plugin_name, plugin_source)
            if spec is None:
                continue
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
        return str(name or "").strip().lower().replace("-", "_")

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

    def _collect_distribution_top_level_modules(
        self,
        dist: importlib_metadata.Distribution,
    ) -> set[str]:
        """提取分发包关联的顶层模块名集合。"""
        modules: set[str] = set()

        try:
            top_level = dist.read_text("top_level.txt")
        except Exception:
            top_level = None

        if isinstance(top_level, str):
            for line in top_level.splitlines():
                name = str(line or "").strip()
                if name:
                    modules.add(name)

        for ep in getattr(dist, "entry_points", []):
            value = str(getattr(ep, "value", "") or "").strip()
            if not value:
                continue
            module_part = value.split(":", 1)[0].strip()
            root_module = module_part.split(".", 1)[0].strip()
            if root_module:
                modules.add(root_module)

        return modules

    def _cleanup_package_from_target(self, package_name: str, target_dir: Path) -> bool:
        """从目标 site-packages 清理指定分发及其顶层模块。

        Args:
            package_name (str): 分发包名。
            target_dir (Path): 目标 site-packages 目录。

        Returns:
            bool: 存在匹配并执行清理时返回 True；未发现匹配分发时返回 False。

        Raises:
            OSError: 删除文件或目录失败时抛出。
        """
        normalized = self._normalize_distribution_name(package_name)
        matched: list[tuple[importlib_metadata.Distribution, set[str]]] = []

        for dist in self._iter_target_distributions(target_dir):
            dist_name = str(getattr(dist, "name", "") or "")
            if self._normalize_distribution_name(dist_name) != normalized:
                continue
            matched.append((dist, self._collect_distribution_top_level_modules(dist)))

        if not matched:
            return False

        for dist, modules in matched:
            dist_files = list(getattr(dist, "files", []) or [])
            for item in dist_files:
                candidate = Path(str(dist.locate_file(item)))
                if candidate.is_file():
                    candidate.unlink(missing_ok=True)
                elif candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)

            for module_name in modules:
                module_dir = target_dir / module_name
                module_py = target_dir / f"{module_name}.py"
                if module_dir.exists() and module_dir.is_dir():
                    shutil.rmtree(module_dir, ignore_errors=True)
                if module_py.exists() and module_py.is_file():
                    module_py.unlink(missing_ok=True)

            dist_name = self._normalize_distribution_name(str(getattr(dist, "name", "") or ""))
            version = str(getattr(dist, "version", "") or "").strip()
            if dist_name and version:
                editable_pth = target_dir / f"__editable__.{dist_name}-{version}.pth"
                editable_pth.unlink(missing_ok=True)

        return True

    async def install_plugin_package(self, package_name: str) -> None:
        """从 PyPI 安装插件包到插件专用 site-packages。

        Args:
            package_name (str): PyPI 包名，例如 auto-mas-test。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 包名非法时抛出。
            RuntimeError: 在以下场景抛出：
                1) 安装命令执行失败；
                2) 安装后未发现任何插件入口点。
        """
        normalized = self._validate_package_name(package_name)
        target_dir = get_pypi_site_packages_dir(self.plugins_dir)

        try:
            await uv_pip_install_with_mirror_fallback([normalized], target=target_dir)
        except RuntimeError as e:
            raise RuntimeError(f"安装插件包失败: package={normalized}, detail={e}") from e

        self.invalidate_discover_cache()
        discovered = await self.discover_plugins(force=True)
        if not discovered:
            raise RuntimeError(
                f"安装完成但未发现插件入口点: package={normalized}，请确认该包声明了 {ENTRY_POINT_GROUPS}"
            )

        logger.info(f"插件包安装完成: package={normalized}")

    async def uninstall_plugin_package(self, package_name: str) -> None:
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
        target_dir = get_pypi_site_packages_dir(self.plugins_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        removed_from_target = self._cleanup_package_from_target(normalized, target_dir)

        completed = await uv_pip_uninstall(normalized, target=target_dir)
        uv_ok = completed.returncode == 0

        if not removed_from_target and not uv_ok:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr or stdout or "未知错误"
            raise RuntimeError(f"卸载插件包失败: package={normalized}, detail={detail}")

        self.invalidate_discover_cache()
        await self.discover_plugins(force=True)
        logger.info(f"插件包卸载完成: package={normalized}, removed_from_target={removed_from_target}")

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

        target_dir = self.plugins_dir / "pypi" / "site-packages"

        try:
            await uv_pip_install([str(package_dir)], target=target_dir)
        except RuntimeError as e:
            raise RuntimeError(
                f"更新 PyPI 插件失败: plugin={plugin_name}, detail={e}"
            ) from e

        logger.info(f"PyPI 插件目录更新完成: plugin={plugin_name}, path={package_dir}")

    async def _update_all_pypi_plugins(self, discovered: Dict[str, Any]) -> None:
        """批量更新已发现的 PyPI 插件。"""
        for plugin_name, plugin_source in discovered.items():
            if getattr(plugin_source, "source", "") != "pypi":
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

    async def ensure_instance_can_delete(
        self,
        instance_id: str,
        *,
        plugin_name: str | None = None,
        discovered: Dict[str, Any] | None = None,
    ) -> None:
        """校验插件实例是否允许删除。"""

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

    async def apply_instance_enabled(self, instance_id: str, enabled: bool) -> None:
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

        schedule_plugin_snapshot(
            reason="manager.apply_instance_enabled",
            discovered=discovered,
        )

    async def start(self) -> None:
        """
        启动插件系统并按配置加载实例。

        Returns:
            None: 无返回值。
        """
        if self.started:
            logger.warning("插件系统已启动，忽略重复启动")
            return

        discovered = await self.discover_plugins()
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        await self.loader.load_instances(instances)
        await self._repair_invalid_instances_after_start(discovered)
        self.started = True
        schedule_plugin_snapshot(reason="manager.start", discovered=discovered)
        logger.info("插件系统启动完成")

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

    async def reload_instance(self, instance_id: str) -> None:
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

        await self._update_pypi_plugin(target.plugin, discovered)

        if target.enabled:
            record = await self.loader.reload_instance(
                instance_id=target.id,
                plugin_name=target.plugin,
                instance_name=target.name,
                config=target.config,
                reason="manager.reload_instance",
            )
            if getattr(record, "status", "") == "error":
                changed = await self._set_instance_enabled(
                    target.id,
                    False,
                    discovered=discovered,
                )
                if changed:
                    logger.warning(
                        f"插件实例重载失败，已自动禁用: instance_id={target.id}, error={record.error}"
                    )
            schedule_plugin_snapshot(
                reason="manager.reload_instance",
                discovered=discovered,
            )
            return

        await self.loader.unload_instance(instance_id)
        schedule_plugin_snapshot(
            reason="manager.reload_instance",
            discovered=discovered,
        )

    async def reload_plugin(self, plugin_name: str) -> None:
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
        await self._update_pypi_plugin(plugin_name, discovered)
        instances = await self.config_store.load_instances(
            self.plugins_dir,
            discovered,
            auto_create_missing=False,
        )
        matched = [item for item in instances if item.plugin == plugin_name]
        if not matched:
            raise ValueError(f"未找到插件实例: {plugin_name}")

        disabled_ids: list[str] = []
        for item in matched:
            if not item.enabled:
                await self.loader.unload_instance(item.id)
                continue
            record = await self.loader.reload_instance(
                instance_id=item.id,
                plugin_name=item.plugin,
                instance_name=item.name,
                config=item.config,
                reason="manager.reload_plugin",
            )
            if getattr(record, "status", "") == "error":
                changed = await self._set_instance_enabled(
                    item.id,
                    False,
                    discovered=discovered,
                )
                if changed:
                    disabled_ids.append(item.id)

        if disabled_ids:
            logger.warning(
                f"插件重载后自动禁用了启动失败实例: {', '.join(disabled_ids)}"
            )
        schedule_plugin_snapshot(
            reason="manager.reload_plugin",
            discovered=discovered,
        )


PluginManager = _PluginManager()
