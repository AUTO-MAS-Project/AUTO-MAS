"""agent 子进程的 pyc 前缀：正常安装路径下设到 <项目根>/.pycache，路径长到会撞 MAX_PATH 时不设。"""

from unittest.mock import patch

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import host_environment as he

SHORT_ROOT = r"C:\Program Files\AUTO-MAS\data\maafw_projects\2d6adb31-8c27-4fb5-951b-42de95f80abd"
LONG_ROOT = (
    r"C:\Users\someone\AppData\Local\Programs\AUTO-MAS\data\maafw_projects"
    r"\2d6adb31-8c27-4fb5-951b-42de95f80abd"
)


def test_prefix_is_set_under_the_project_root() -> None:
    env: dict[str, str] = {}
    with patch.object(he, "_windows_long_paths_enabled", return_value=False):
        he.set_project_pycache_prefix(env, SHORT_ROOT)
    assert env["PYTHONPYCACHEPREFIX"] == SHORT_ROOT + "\\" + he.PROJECT_PYCACHE_DIR_NAME


def test_long_root_without_long_path_support_skips_the_prefix() -> None:
    # 前缀树里项目根出现两遍，超过 MAX_PATH 时解释器写 pyc 静默失败——不如不设。
    env = {"PYTHONPYCACHEPREFIX": "stale"}
    with patch.object(he, "_windows_long_paths_enabled", return_value=False):
        he.set_project_pycache_prefix(env, LONG_ROOT)
    assert "PYTHONPYCACHEPREFIX" not in env


def test_long_root_with_long_path_support_keeps_the_prefix() -> None:
    env: dict[str, str] = {}
    with patch.object(he, "_windows_long_paths_enabled", return_value=True):
        he.set_project_pycache_prefix(env, LONG_ROOT)
    assert env["PYTHONPYCACHEPREFIX"].endswith(he.PROJECT_PYCACHE_DIR_NAME)
