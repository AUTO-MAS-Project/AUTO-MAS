import importlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

import app.task
from app.core.config import RESTORE_POOL_MODULE_BOOK, Config
from app.models.config import CLASS_BOOK, MaaConfig


def test_restore_pool_book_covers_every_script_domain() -> None:
    assert set(RESTORE_POOL_MODULE_BOOK) == set(CLASS_BOOK.values())


def test_restore_pool_modules_expose_pools() -> None:
    for module_name in RESTORE_POOL_MODULE_BOOK.values():
        pools = getattr(importlib.import_module(module_name), "RESTORE_POOLS")
        assert isinstance(pools, list)


def test_restore_pool_book_maps_script_types_to_own_task_folder() -> None:
    """每个脚本域的恢复池必须挂在自己的任务目录下。

    注册表映射到「别的域但存在」的模块时，既有导入测试发现不了，本测试
    按任务目录名（与脚本类型大小写不敏感相等）逐项对账。
    """

    task_folders = {
        path.name.lower(): path.name
        for path in Path(app.task.__file__).parent.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }
    for script_type, config_cls in CLASS_BOOK.items():
        folder = task_folders[script_type.lower()]
        assert RESTORE_POOL_MODULE_BOOK[config_cls] == (
            f"app.task.{folder}.tools.restore_service"
        )


def test_restore_service_dispatches_by_script_config_type() -> None:
    """全链分发：按脚本配置实例查注册表，延迟导入对应域恢复池并绑定上下文。"""

    script_id = str(uuid.uuid4())
    with patch.object(Config, "ScriptConfig", {uuid.UUID(script_id): MaaConfig()}):
        service = Config.restore_service(script_id, "user-1")

    assert service.target_keys == ["mas", "native"]


def test_restore_service_rejects_unregistered_script_config() -> None:
    """缺失注册的失败模式：明确报错，不落任何默认池。"""

    class _UnknownConfig:
        pass

    script_id = str(uuid.uuid4())
    with (
        patch.object(Config, "ScriptConfig", {uuid.UUID(script_id): _UnknownConfig()}),
        pytest.raises(ValueError, match=r"该专项暂不支持配置恢复"),
    ):
        Config.restore_service(script_id, "user-1")
