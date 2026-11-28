"""后端测试的配置持久化与应用目录隔离。"""

import sys
from pathlib import Path

# SDK 跟随当前宿主源码，专项回归消费已发布发行包，准备过程不污染运行期插件目录。
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "plugins/auto_mas_core/src"))
sys.path.insert(0, str(root / ".test-plugins"))

import pytest  # noqa: E402 - 插件源码路径须在加载测试依赖前登记。

from app.config import config_manager  # noqa: E402


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
    from app.plugin.runtime import discover

    monkeypatch.setattr(Config, "work_path", tmp_path)
    monkeypatch.setattr(Config, "install_path", tmp_path)
    for attribute, directory in {
        "config_path": "config",
        "temp_path": "temp",
        "data_path": "data",
        "debug_path": "debug",
        "history_path": "history",
        "script_path": "script",
        "plugins_path": "plugins",
    }.items():
        monkeypatch.setattr(Config, attribute, tmp_path / directory)
    monkeypatch.setattr(Config, "log_path", Config.debug_path / "app.log")
    monkeypatch.setattr(Config, "database_path", Config.data_path / "data.db")
    source_projects = discover._source_projects
    checkout_plugins = (root / "plugins").resolve()

    def isolated_projects():
        # _source_projects() 返回的是 resolve() 后的真实路径：本机 plugins/ 下用
        # junction 挂的其它仓库工程会解析到仓库外，旧的「父目录不等于 checkout 的
        # plugins/」判据认不出来，会把它们当成本机工程带进用例。这里改成先解析出
        # checkout 的 plugins/ 直属子工程再比对。
        checkout_children = {child.resolve() for child in checkout_plugins.iterdir()}
        return {
            project
            for project in source_projects()
            if project not in checkout_children or project.name == "auto_mas_core"
        }

    monkeypatch.setattr(discover, "_source_projects", isolated_projects)
    for directory in (Config.config_path, Config.data_path, Config.debug_path):
        directory.mkdir(parents=True, exist_ok=True)
    return Config
