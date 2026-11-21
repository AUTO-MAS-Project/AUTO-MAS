"""在普通 E2E 隔离根中准备发行插件和可查询的历史记录。"""

import asyncio
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import config_manager  # noqa: E402
from app.core import Config, Plugin  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.models.schema import HistoryWrite  # noqa: E402


def bind_script_handlers() -> None:
    """有托管的隔离副本和后端启动使用相同的专项初始化入口。"""
    from app.task.builtin_registration import build_builtin_script_capabilities
    from app.task.MaaEnd.api_service import MaaEndConfigService
    from app.task.ZzzOd.config_context import ZzzOdContext
    from app.task.ZzzOd.recovery import ZzzOdRecovery
    from app.utils.common.game_resolution import (
        read_unity_display_type,
        read_unity_resolution,
    )

    capabilities = build_builtin_script_capabilities(
        maaend=MaaEndConfigService(
            scripts=Config.ScriptConfig,
            read_resolution=read_unity_resolution,
            read_display_type=read_unity_display_type,
        ),
        zzzod=ZzzOdRecovery(
            ZzzOdContext(
                Config.ScriptConfig, flush=Config.flush, add_user=Config.add_user
            )
        ),
    )
    for entry_type, handler in capabilities.config_handlers:
        Config.bind_script_config_handler(entry_type, handler)


async def main() -> None:
    """从隔离测试发行包装配浏览器环境，保留正常插件初始化、启用和配置写盘流程。"""
    test_plugins = Path(__file__).resolve().parents[3] / ".test-plugins"
    repo_plugins = Config.source_path / "plugins"
    source_projects = os.environ.get("AUTO_MAS_E2E_PLUGIN_PROJECTS")
    if source_projects:
        for project in Path(source_projects).iterdir():
            if (
                project.name == "auto_mas_core"
                or not (project / "pyproject.toml").is_file()
            ):
                continue
            if project.resolve() == (repo_plugins / project.name).resolve():
                continue  # 宿主已发现该工作树的源码项目。
            shutil.copytree(
                project,
                Config.plugins_path / project.name,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    ".git", "build", "*.egg-info", "__pycache__"
                ),
            )
    else:
        for name in ("maa_adapter", "src_adapter"):
            if (repo_plugins / name / "pyproject.toml").is_file():
                continue
            if not (test_plugins / name).is_dir():
                raise RuntimeError("请先运行 python scripts/prepare_test_plugins.py")
            for source in test_plugins.glob(f"*{name}*"):
                if source.is_dir():
                    shutil.copytree(
                        source,
                        Config.plugins_path / "pypi" / "site-packages" / source.name,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"),
                    )
    # 首次配置升级会清理旧历史，先走正式迁移，再写入现行格式的种子。
    bind_script_handlers()
    await Config.check_data(prepare_plugins=Plugin.initialize)
    for name in ("maa_adapter", "src_adapter"):
        await Plugin.enable(Config.plugin_registry.by_name(name))
    if source_projects:
        for name in (
            "mumu_adapter",
            "ldplayer_adapter",
            "mod_avd_adapter",
            "general_emulator_adapter",
            "win_process_adapter",
        ):
            await Plugin.enable(Config.plugin_registry.by_name(name))
    await config_manager.flush()
    if "--plugins-only" in sys.argv:
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
