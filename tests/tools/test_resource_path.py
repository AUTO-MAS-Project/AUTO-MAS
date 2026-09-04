"""app/utils/paths.py 源码相对资源解析的回归测试。

受监督布局下（AUTO-MAS-Runtime 拉起）源码目录与工作目录分离：源码在
``<app-root>/repo/`` 子目录，工作目录是 ``<app-root>/``。res/ 下的内置资源
必须按源码位置解析，不能再假设等于 Path.cwd()。
"""

from app.utils import resource_path
from app.utils.paths import SOURCE_ROOT


def test_source_root_points_at_repository_root() -> None:
    """parents 层级算对了：SOURCE_ROOT 应是仓库根，main.py 就在其下。"""

    assert (SOURCE_ROOT / "main.py").is_file()


def test_resource_path_ignores_cwd(monkeypatch, tmp_path) -> None:
    """chdir 到与源码树无关的临时目录后，resource_path 仍能定位真实资源目录。"""

    monkeypatch.chdir(tmp_path)

    materials_dir = resource_path("images", "materials")

    assert materials_dir == SOURCE_ROOT / "res" / "images" / "materials"
    assert materials_dir.is_dir()


def test_resource_path_joins_arbitrary_parts(monkeypatch, tmp_path) -> None:
    """多段 parts 依次拼在 res/ 之后，与 Path.joinpath 语义一致。"""

    monkeypatch.chdir(tmp_path)

    version_path = resource_path("version.json")

    assert version_path == SOURCE_ROOT / "res" / "version.json"
    assert version_path.is_file()
