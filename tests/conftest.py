"""本地迁移验证中隔离持久化根，避免前一测试的临时文件参与后续落盘。"""

import pytest

from app.config import config_manager


@pytest.fixture(autouse=True)
def isolated_config_roots():
    roots = dict(config_manager._roots)
    config_manager._roots.clear()
    yield
    handle = config_manager._save_handle
    if handle is not None and not handle.done() and not handle.get_loop().is_closed():
        handle.cancel()
    config_manager._save_handle = None
    config_manager._roots.clear()
    config_manager._roots.update(roots)
