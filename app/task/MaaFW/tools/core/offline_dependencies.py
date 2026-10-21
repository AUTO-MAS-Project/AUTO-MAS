"""项目自带的依赖安装材料：离线依赖包（``*.whl`` / ``get-pip.py``）与依赖清单。

两处共用同一套判据：

- 投影（``project_update.projection``）：超过 64 MB 的没声明的顶层目录里有离线依赖包，就按
  离线依赖目录整棵带进载荷（agent 首次启动从这里离线装依赖，丢了就装不上）。
- 准备运行环境（``agent_env.env``）：项目自带 Python 里还导入不了 MaaFW Agent 模块时，项目
  带着这些材料就说明是「agent 第一次启动时自己装依赖」的写法（MaaDuDuL、MaaTOT、
  MaaStarResonance：``pip install -r requirements.txt`` / ``get-pip.py`` + ``deps/*.whl``），
  照常起 agent，由它自己装（MFAA / MXU 对这类项目也是这样）。

放在 ``tools/core`` 根下而不是 ``project_update``：agent 环境准备在 worker 的导入闭包里，
``project_update`` 包的初始化会引到宿主模块（见 MaaFW/AGENTS.md）。只依赖标准库。
"""

from __future__ import annotations

from pathlib import Path, PurePath

# 离线依赖包只认这个深度以内（0 = 直接放在顶层目录里）的：语料里真正的离线依赖目录
# wheel 都在这两层（MHXY、MaaGumballs 等是 ``deps/*.whl``，MaaStarResonance 另有
# ``deps/<子目录>/*.whl``）；更深处的是别的东西顺带解压出来的——M9A 自更新留下的
# ``temp_res/resource_v3.22.0_extracted/deps/*.whl`` 曾让整个 185 MB 的 ``temp_res/``
# 绕过 64 MB 上限进了副本。
OFFLINE_DEPENDENCY_MAX_DEPTH = 1

#: 项目根上的依赖清单：agent 首次启动时 ``pip install -r`` / ``pip install <项目>`` 的输入。
DEPENDENCY_MANIFEST_NAMES = ("requirements.txt", "pyproject.toml")


def is_cpython_bundled_file(path: PurePath) -> bool:
    """路径在 CPython 自带的 ``ensurepip/`` 或标准库测试套件 ``Lib/test/`` 之下。

    ``ensurepip/_bundled``（venv / 安装器附带 pip），以及 python.org 安装器默认装上的
    测试套件 ``Lib/test/**``（``wheeldata``、``test_importlib/data`` 里都有 .whl）都不是
    项目的离线依赖包。
    """

    parts = [part.casefold() for part in path.parts]
    if "ensurepip" in parts:
        return True
    return any(
        part == "lib" and following == "test"
        for part, following in zip(parts, parts[1:])
    )


def is_offline_dependency_file(path: PurePath, *, depth: int) -> bool:
    """``path`` 是不是离线依赖包（``*.whl`` 或 ``get-pip.py``）。

    ``depth``：它在所属顶层目录下的层数（直接放在顶层目录里是 1），超过
    ``OFFLINE_DEPENDENCY_MAX_DEPTH + 1`` 的不算；CPython 自带的不算。
    """

    return (
        (path.suffix.casefold() == ".whl" or path.name.casefold() == "get-pip.py")
        and depth <= OFFLINE_DEPENDENCY_MAX_DEPTH + 1
        and not is_cpython_bundled_file(path)
    )


def _offline_dependency_files(directory: Path, relative: PurePath) -> list[str]:
    """顶层目录里深度以内的离线依赖包（相对项目根，posix）。只往下看一层，不整棵遍历。"""

    found: list[str] = []
    pending: list[tuple[Path, PurePath, int]] = [(directory, relative, 1)]
    while pending:
        current, current_rel, depth = pending.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            entry_rel = current_rel / entry.name
            try:
                if entry.is_file():
                    if is_offline_dependency_file(entry_rel, depth=depth):
                        found.append(entry_rel.as_posix())
                elif (
                    entry.is_dir()
                    and not entry.is_symlink()
                    and depth <= OFFLINE_DEPENDENCY_MAX_DEPTH
                ):
                    pending.append((entry, entry_rel, depth + 1))
            except OSError:
                continue
    return sorted(found)


def describe_self_install_materials(project_root: str | Path) -> str | None:
    """项目带着「首次启动自己装依赖」的材料时返回一句说明（列出找到的文件），否则 None。

    认三样：项目根上的 ``requirements.txt`` / ``pyproject.toml``；顶层目录里（深度以内）的
    ``*.whl``；``get-pip.py``。与投影不同，项目自带的解释器目录里的 ``get-pip.py``（MaaFgo 把它
    放在 ``python/`` 下）也算：这里问的是「项目会不会自己装」，不是「要不要整棵带走」。
    """

    root = Path(project_root)
    found = [name for name in DEPENDENCY_MANIFEST_NAMES if (root / name).is_file()]
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        try:
            if entry.is_dir() and not entry.is_symlink():
                found.extend(_offline_dependency_files(entry, PurePath(entry.name)))
        except OSError:
            continue
    if not found:
        return None
    shown = found[:5]
    more = f" 等 {len(found)} 个" if len(found) > len(shown) else ""
    return "、".join(shown) + more


__all__ = [
    "DEPENDENCY_MANIFEST_NAMES",
    "OFFLINE_DEPENDENCY_MAX_DEPTH",
    "describe_self_install_materials",
    "is_cpython_bundled_file",
    "is_offline_dependency_file",
]
