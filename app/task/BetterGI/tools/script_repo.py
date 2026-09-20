#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 脚本仓库浏览与订阅（A+ 方案）。

BetterGI 的脚本仓库**不是**本地 git 克隆出脚本文件：BGI 的 ``ScriptRepoUpdater``
从远程下载仓库 zip，但本地 ``{RootPath}/Repos/bettergi-scripts-list/`` 只留一份
**索引文件** ``repo.json``——一棵 ``indexes`` 树（``js`` / ``pathing`` / ``combat`` /
``tcg`` 等分类，节点含 ``version`` / ``author`` / ``description`` / ``tags`` /
``lastUpdated`` 元数据），脚本本体在订阅时才从远程拉取。

本模块提供两条 MAS 侧能力：

- ``list_repo_catalog``：解析 ``repo.json`` 索引树，返回分类 + 节点树（递归标注
  ``path`` 供订阅定位），供前端「浏览脚本仓库」面板展示。
- ``subscribe_script``：对指定仓库相对路径（如 ``js/AAA-Artifacts-Bulk-Supply``、
  ``pathing/锄地专区/xxx/A01-xxx.json``）：
  1. **总是**写 BGI 原生订阅清单 ``User/Subscriptions/bettergi-scripts-list.json``
     （与切号脚本同格式，BGI 后续自动更新仍能维护该脚本）；
  2. 是否**立即落地**由 ``immediate`` 控制（默认 ``False``）：
     - ``immediate=False``（默认、轻量）：仅写入订阅清单，不下载、不落地。脚本本体
       由 BetterGI 下次启动时按其原生订阅链路自动拉取——与 BGI 原生订阅行为完全一致，
       无需等待仓库压缩包下载；
     - ``immediate=True``（进阶、立即可用）：额外下载仓库 zip 到 MAS 缓存（按索引
       ``time`` 增量缓存），解压出对应脚本子树，拷贝到 BGI 原生目录
       （``User/JsScript`` / ``User/AutoPathing`` / ``User/AutoFight`` /
       ``User/AutoGeniusInvokation``，按分类映射、保留分类内相对路径），使脚本立刻可用。

默认走轻量路径，避免每次订阅都强制下载整个仓库压缩包（远程是单整仓，无单脚本直链，
订阅任意脚本都需先拉整包，因此默认交由 BGI 自身拉取更省事）；仅当用户希望「点完立刻
就能在 BGI 里用」时才触发一次下载落地（之后复用缓存）。

⚠️ 与 BGI 写入冲突：拷贝目标为 BGI ``User/`` 目录，须在 BGI 未运行时执行
（MAS 既有的 ``User/`` 写操作均遵守此约定）。若目标已存在则跳过拷贝，避免覆盖
用户可能已修改的内容，但仍保证订阅记录就绪。
"""

import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

import httpx

from app.utils import get_logger
from app.utils.io import read_file, write_file

logger = get_logger("BetterGI 脚本仓库")

# BGI 本地仓库索引文件（由 BGI ScriptRepoUpdater 下载维护）
_INDEX_FILE = Path("Repos") / "bettergi-scripts-list" / "repo.json"
_SUBSCRIPTION_FILE = Path("User") / "Subscriptions" / "bettergi-scripts-list.json"

# 仓库顶层分类 -> (中文分类名, BGI 原生目标目录相对路径)
# 原生目标目录与 BGI 的 ImportScriptFromUri 落盘映射一致
_CATEGORY_MAP: dict[str, tuple[str, Path]] = {
    "js": ("JS 脚本", Path("User") / "JsScript"),
    "pathing": ("地图追踪", Path("User") / "AutoPathing"),
    "combat": ("自动战斗", Path("User") / "AutoFight"),
    "tcg": ("七圣召唤", Path("User") / "AutoGeniusInvokation"),
}

# MAS 侧仓库 zip 缓存目录（相对项目根），按索引 time 增量复用
_CACHE_SUBDIR = Path("data") / "cache" / "bettergi-scripts-list"


def _validate_script_id(script_id: str) -> str:
    """校验脚本 ID 可安全拼入 ``data/`` 相对路径：必须是合法 UUID。"""

    value = str(script_id or "").strip()
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise ValueError("脚本 ID 不合法") from e
    return value


def _annotate(node: dict[str, Any], parent: str) -> dict[str, Any]:
    """递归为索引节点标注 ``path``（仓库相对路径，供订阅定位）。"""

    path = f"{parent}/{node['name']}" if parent else str(node["name"])
    out: dict[str, Any] = {
        "name": node.get("name") or "",
        "type": node.get("type") or "file",
        "path": path,
        "version": node.get("version") or "",
        "author": node.get("author") or "",
        "description": node.get("description") or "",
        "tags": [str(t) for t in (node.get("tags") or [])],
        "lastUpdated": node.get("lastUpdated") or "",
        "children": [],
    }
    for child in node.get("children") or []:
        if isinstance(child, dict):
            out["children"].append(_annotate(child, path))
    return out


def load_index(root: Path) -> Optional[dict[str, Any]]:
    """读取 BGI 本地仓库索引 ``repo.json``；缺失返回 ``None``。

    索引由 BetterGI 在用户打开脚本仓库时从远程下载维护，MAS 不自行拉取索引。
    """

    data = read_file(root / _INDEX_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("indexes"), list):
        return None
    return data


def list_repo_catalog(root: Path) -> dict[str, Any]:
    """解析仓库索引，返回分类 + 节点树（递归含 ``path``）。

    Returns:
        ``{"repo_exists": bool, "update_time": 索引时间, "repo_url": 仓库 zip 地址,
        "categories": {分类键: {"label": 中文名, "tree": [节点树]}}}``。
        索引缺失时 ``repo_exists=False``。
    """

    index = load_index(root)
    if index is None:
        return {
            "repo_exists": False,
            "update_time": "",
            "repo_url": "",
            "categories": {},
        }
    categories: dict[str, Any] = {}
    for top in index["indexes"]:
        if not isinstance(top, dict) or not top.get("name"):
            continue
        key = str(top["name"])
        label = _CATEGORY_MAP.get(key, (key, None))[0]
        categories[key] = {
            "label": label,
            "tree": [
                _annotate(child, key)
                for child in (top.get("children") or [])
                if isinstance(child, dict)
            ],
        }
    return {
        "repo_exists": True,
        "update_time": str(index.get("time") or ""),
        "repo_url": str(index.get("url") or ""),
        "categories": categories,
    }


def _zip_fixed_name(name: str) -> str:
    """还原 zip 条目文件名。

    ``zipfile`` 对未设 UTF-8 标志的条目按 cp437 解码（中文会乱码）：
    能被 cp437 重新编码的，按 UTF-8（失败再 GBK）还原；否则说明原名即正确 Unicode。
    """

    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", "replace")


def _extract_repo_zip(zip_path: Path, dest: Path) -> None:
    """解压仓库 zip 到 ``dest``（展平唯一顶层目录，修复中文文件名编码）。"""

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = Path(_zip_fixed_name(info.filename))
            parts = rel.parts[1:] if len(rel.parts) > 1 else rel.parts
            if not parts:
                continue
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))


async def _download_file(url: str, dest: Path) -> None:
    """流式下载仓库 zip 到 ``dest``。"""

    dest.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                async for chunk in resp.aiter_bytes(1 << 16):
                    f.write(chunk)
            tmp.replace(dest)


async def _ensure_repo_cache(
    root: Path, index_time: str, repo_url: str
) -> Path:
    """确保仓库 zip 已下载并解压到 MAS 缓存，返回解压根目录。

    缓存以索引 ``time`` 为版本号：一致直接复用，不一致重新下载解压。
    """

    cache_zip = _CACHE_SUBDIR / "repo.zip"
    cache_root = _CACHE_SUBDIR / "extracted"
    stamp = _CACHE_SUBDIR / "time.txt"
    if cache_root.is_dir() and stamp.is_file() and stamp.read_text("utf-8").strip() == index_time:
        return cache_root
    if not repo_url:
        raise RuntimeError("仓库索引缺少下载地址")
    logger.info(f"下载脚本仓库压缩包: {repo_url}")
    await _download_file(repo_url, cache_zip)
    logger.info(f"解压脚本仓库缓存: {cache_zip} -> {cache_root}")
    _extract_repo_zip(cache_zip, cache_root)
    _CACHE_SUBDIR.mkdir(parents=True, exist_ok=True)
    stamp.write_text(index_time, "utf-8")
    return cache_root


def _find_index_node(categories: dict[str, Any], rel_path: str) -> Optional[dict[str, Any]]:
    """在已标注 ``path`` 的分类树中查找仓库相对路径对应的节点。"""

    parts = rel_path.split("/")
    if not parts:
        return None
    category = categories.get(parts[0])
    if not category:
        return None
    stack = list(category["tree"])
    while stack:
        node = stack.pop()
        if node["path"] == rel_path:
            return node
        stack.extend(node["children"])
    return None


async def subscribe_script(
    root: Path, script_id: str, rel_path: str, immediate: bool = False
) -> dict[str, Any]:
    """订阅仓库中指定脚本：写订阅清单，并视 ``immediate`` 决定是否立即落地。

    Args:
        root: BetterGI RootPath。
        script_id: MAS 脚本 ID（用于缓存目录隔离）。
        rel_path: 仓库相对路径，如 ``js/AAA-Artifacts-Bulk-Supply`` 或
            ``pathing/锄地专区/xxx/A01-xxx.json``。
        immediate: 是否立即下载仓库压缩包并落地到 BGI 原生目录。默认 ``False``：
            仅写入 BGI 原生订阅清单，脚本本体由 BetterGI 下次启动自动拉取。

    Returns:
        ``{"subscribed": 订阅相对路径, "native_path": 原生目标绝对路径,
        "already_existed": 原生目标是否已存在, "copied": 本次是否执行了拷贝,
        "immediate": 本次是否执行了落地}``。

    Raises:
        ValueError: 路径不合法或分类不支持。
        FileNotFoundError: 索引或缓存中不存在该路径。
        RuntimeError: 仓库索引缺失（需先在 BGI 打开脚本仓库）。
    """

    rel_path = str(rel_path or "").strip().replace("\\", "/").strip("/")
    if not rel_path or ".." in rel_path.split("/"):
        raise ValueError("脚本仓库路径不合法")
    category = rel_path.split("/")[0]
    if category not in _CATEGORY_MAP:
        raise ValueError(f"不支持的脚本分类: {category}")
    _, native_rel = _CATEGORY_MAP[category]

    index = load_index(root)
    if index is None:
        raise RuntimeError("本地仓库索引缺失，请先在 BetterGI 内打开脚本仓库")
    catalog = list_repo_catalog(root)
    node = _find_index_node(catalog["categories"], rel_path)
    if node is None:
        raise FileNotFoundError(f"仓库索引中不存在: {rel_path}")

    # 1. 总是写 BGI 原生订阅清单（数组，存仓库相对路径，与切号脚本同格式）
    sub_path = root / _SUBSCRIPTION_FILE
    subscribed: list[str] = []
    existing = read_file(sub_path)
    if isinstance(existing, list):
        subscribed = [str(x) for x in existing]
    if rel_path not in subscribed:
        subscribed.append(rel_path)
        write_file(sub_path, subscribed)
        logger.info(f"已写入订阅清单: {rel_path} -> {sub_path}")
    else:
        logger.info(f"订阅清单已含: {rel_path}")

    # 2. 是否立即落地：默认轻量（不下载）；仅 immediate=True 才下载仓库压缩包并拷贝
    if not immediate:
        logger.info(f"轻量订阅（仅记录），交由 BetterGI 启动后自动拉取: {rel_path}")
        return {
            "subscribed": rel_path,
            "native_path": "",
            "already_existed": False,
            "copied": False,
            "immediate": False,
        }

    cache_root = await _ensure_repo_cache(root, catalog["update_time"], catalog["repo_url"])
    src = cache_root.joinpath(*rel_path.split("/"))
    if not src.exists():
        raise FileNotFoundError(f"仓库压缩包中不存在: {rel_path}")
    rel_in_category = "/".join(rel_path.split("/")[1:])
    if not rel_in_category:
        raise ValueError("订阅路径缺少分类后的脚本名")
    dest = root / native_rel / rel_in_category
    copied = False
    if dest.exists():
        logger.info(f"原生目录已存在，跳过拷贝（保留现有内容）: {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        copied = True
        logger.info(f"已从仓库落地脚本到原生目录: {src} -> {dest}")
    return {
        "subscribed": rel_path,
        "native_path": str(dest),
        "already_existed": dest.exists(),
        "copied": copied,
        "immediate": True,
    }
