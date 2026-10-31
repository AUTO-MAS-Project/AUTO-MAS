"""后端测试的配置持久化与应用目录隔离。"""

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


@pytest.fixture
def isolated_app_paths(tmp_path, monkeypatch):
    """为需要真实 Config 路径的测试隔离用户目录，保留源码及内置资源位置。"""
    from app.core import Config

    monkeypatch.setattr(Config, "work_path", tmp_path)
    monkeypatch.setattr(Config, "install_path", tmp_path)
    for attribute, directory in {
        "config_path": "config",
        "data_path": "data",
        "debug_path": "debug",
        "history_path": "history",
        "script_path": "script",
        "plugins_path": "plugins",
    }.items():
        monkeypatch.setattr(Config, attribute, tmp_path / directory)
    monkeypatch.setattr(Config, "log_path", Config.debug_path / "app.log")
    monkeypatch.setattr(Config, "database_path", Config.data_path / "data.db")
    for directory in (Config.config_path, Config.data_path, Config.debug_path):
        directory.mkdir(parents=True, exist_ok=True)
    return Config
