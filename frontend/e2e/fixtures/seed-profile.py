"""在普通 E2E 隔离根中准备发行插件和可查询的历史记录。"""

import asyncio
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import config_manager  # noqa: E402
from app.core import Config, Plugin  # noqa: E402
from app.core.history import HistoryStore  # noqa: E402
from app.models.schema import HistoryWrite  # noqa: E402


async def main() -> None:
    """从隔离测试发行包装配浏览器环境，保留正常插件初始化、启用和配置写盘流程。"""
    test_plugins = Path(__file__).resolve().parents[3] / ".test-plugins"
    if not (test_plugins / "maa_adapter").is_dir():
        raise RuntimeError(
            "请先运行 uv run --no-sync python scripts/prepare_test_plugins.py"
        )
    shutil.copytree(
        test_plugins,
        Config.plugins_path / "pypi" / "site-packages",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # 首次配置升级会清理旧历史，先走正式迁移，再写入现行格式的种子。
    await Config.check_data(prepare_plugins=Plugin.initialize)
    await Plugin.enable(Config.plugin_registry.by_name("maa_adapter"))
    await config_manager.flush()
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
