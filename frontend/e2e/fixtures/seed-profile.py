"""在普通 E2E 隔离根中准备发行插件和可查询的历史记录。"""

import asyncio
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

from packaging.utils import parse_wheel_filename

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import config_manager  # noqa: E402
from app.core import Config, Plugin  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.models.schema import HistoryWrite  # noqa: E402

BROWSER_ADAPTERS = ("maa_adapter", "src_adapter", "bettergi_adapter", "whimbox_adapter")
GAME_ADAPTERS = (
    "mumu_adapter",
    "ldplayer_adapter",
    "mod_avd_adapter",
    "general_emulator_adapter",
    "win_process_adapter",
)
MAAEND_ADAPTER = "maaend_adapter"


def copy_source_projects(projects_root: Path, repo_plugins: Path) -> None:
    """把源码工程复制到隔离根，已经由宿主源码发现的工程不重复复制。"""
    projects = (
        [projects_root]
        if (projects_root / "pyproject.toml").is_file()
        else sorted(projects_root.iterdir())
    )
    projects = [
        project for project in projects if (project / "pyproject.toml").is_file()
    ]
    if not projects:
        raise RuntimeError(f"未找到插件源码工程：{projects_root}")
    repo_projects = {project.resolve() for project in repo_plugins.iterdir()}
    for project in projects:
        if project.name == "auto_mas_core" or project.resolve() in repo_projects:
            continue
        shutil.copytree(
            project,
            Config.plugins_path / project.name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", "build", "dist", "*.egg-info", "__pycache__"
            ),
        )


def source_adapter_names(*roots: Path) -> set[str]:
    """按项目声明识别插件，允许使用普通 Git 检出目录名。"""
    names = set()
    for root in roots:
        for pyproject in root.glob("*/pyproject.toml"):
            with pyproject.open("rb") as file:
                keywords = tomllib.load(file).get("project", {}).get("keywords", [])
            if "auto-mas-plugin" in keywords:
                names.update(
                    keyword.removeprefix("auto-mas-id:")
                    for keyword in keywords
                    if keyword.startswith("auto-mas-id:")
                )
    return names


def install_fixture_wheels(sources: dict[str, Path], site_packages: Path) -> None:
    """把待测 wheel 固定到隔离目录，让预装和宿主依赖求解使用同一份文件。"""
    wheels = site_packages.parent / "fixture-wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    requirements = []
    files = []
    for package, wheel in sources.items():
        if not wheel.is_file() or parse_wheel_filename(wheel.name)[0] != package:
            raise RuntimeError(f"请提供 {package} 的 wheel 文件：{wheel}")
        local_wheel = wheels / wheel.name
        shutil.copy2(wheel, local_wheel)
        requirements.append(f"{package} @ {local_wheel.as_uri()}")
        files.append(str(local_wheel))
    (site_packages.parent / "e2e-wheel-requirements.txt").write_text(
        "\n".join(requirements) + "\n", encoding="utf-8"
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(site_packages),
            "--no-deps",
            "--no-index",
            *files,
        ],
        check=True,
    )


def bind_script_handlers() -> None:
    """有托管的隔离副本和后端启动使用相同的专项初始化入口。"""
    from app.task.builtin_registration import build_builtin_script_capabilities

    capabilities = build_builtin_script_capabilities()
    for entry_type, handler in capabilities.config_handlers:
        Config.bind_script_config_handler(entry_type, handler)


async def main() -> None:
    """从隔离测试发行包装配浏览器环境，保留正常插件初始化、启用和配置写盘流程。"""
    test_plugins = Path(__file__).resolve().parents[3] / ".test-plugins"
    repo_plugins = Config.source_path / "plugins"
    site_packages = Config.plugins_path / "pypi" / "site-packages"
    plugins_only = "--plugins-only" in sys.argv
    if source_projects := os.environ.get("AUTO_MAS_E2E_PLUGIN_PROJECTS"):
        copy_source_projects(Path(source_projects), repo_plugins)
    local = source_adapter_names(repo_plugins, Config.plugins_path)
    names = [name for name in GAME_ADAPTERS if name in local]
    names.extend(name for name in (MAAEND_ADAPTER, "zzzod_adapter") if name in local)
    wheel_sources = {}
    for name, package, variable in (
        (MAAEND_ADAPTER, "auto-mas-maaend-adapter", "AUTO_MAS_E2E_MAAEND_WHEEL"),
        ("baah_adapter", "auto-mas-baah-adapter", "AUTO_MAS_E2E_BAAH_WHEEL"),
    ):
        if wheel := os.environ.get(variable):
            if name in local:
                raise RuntimeError(f"{name} 源码与 wheel 同时提供，请只选一种来源")
            wheel_sources[package] = Path(wheel)
            names.append(name)
    if wheel_sources:
        install_fixture_wheels(wheel_sources, site_packages)
    for name in BROWSER_ADAPTERS:
        if name not in local and not plugins_only:
            if not (test_plugins / name).is_dir():
                raise RuntimeError(
                    "请先运行 uv run --no-sync python scripts/prepare_test_plugins.py"
                )
            for source in test_plugins.glob(f"*{name}*"):
                if source.is_dir():
                    shutil.copytree(
                        source,
                        site_packages / source.name,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"),
                    )
        if name in local or not plugins_only:
            names.append(name)
    # 首次配置升级会清理旧历史，先走正式迁移，再写入现行格式的种子。
    bind_script_handlers()
    await Config.check_data(prepare_plugins=Plugin.initialize)
    for name in names:
        record = Config.plugin_registry.by_name(name)
        if record is None:
            raise RuntimeError(f"隔离浏览器环境未发现指定插件：{name}")
        await Plugin.enable(record)
    await config_manager.flush()
    if plugins_only:
        await Plugin.shutdown()
        await config_manager.flush()
        return
    store = HistoryStore()
    await store.initialize(video_limit_bytes=0)
    today = (
        datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    )
    try:
        for days, account, marker in [
            (0, "History account A", "E2E_TODAY_SUCCESS"),
            (1, "History account A", "E2E_YESTERDAY_FAILURE"),
            (8, "History account B", "E2E_OLDER_SUCCESS"),
        ]:
            record = await store.record(
                HistoryWrite(
                    time=today - timedelta(days=days),
                    username=account,
                    script_name="E2E history script",
                    status="error" if days == 1 else "success",
                    message=marker,
                    logs=f"[INFO] {marker}\n",
                )
            )
            detail = await store.get_detail(record_id=record.id)
            assert detail.log_available and marker in (detail.log_content or "")
            assert not record.storage_errors
    finally:
        await store.close()
        await Plugin.shutdown()
        await config_manager.flush()


if __name__ == "__main__":
    asyncio.run(main())
