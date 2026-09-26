"""Contracts shared by the resumable MaaFW project updater."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

ArtifactType = Literal["full", "delta"]
RESERVED_PROJECT_DIRS = frozenset({".mas-update", ".mas-update-cache"})

# 指纹只回答「项目是否还是我们装下去的那份」，必须排除运行期产物：MaaFW 每次启动都往
# 项目目录写 debug/ 日志，runner 还会重写 config/maa_option.json，Python agent 会留下
# __pycache__（agent 子进程设了 PYTHONPYCACHEPREFIX 之后全在项目根的 .pycache/ 下，
# 那棵镜像树里没有 __pycache__ 这一层，要单独列）。把它们算进哈希，项目跑过一次后差量
# 更新的基线校验就永远对不上，而那条路径没有回退全量包的分支——Mirror 酱源于是再也装不上
# 更新。与 RESERVED_PROJECT_DIRS 分开：那个还用于拒绝更新包写入保留路径，把运行期目录
# 塞进去会让本来就带 config/ 的合法包直接装不上。
FINGERPRINT_IGNORED_DIRS = frozenset(
    {"debug", "logs", "temp", "__pycache__", ".pycache"}
)
# ``.auto_mas_view.json`` 是视图标记（记这棵视图挂在哪个载荷上），MAS 自己的簿记，
# 不是项目内容；随切换原子换入，每次都不同。
VIEW_MARKER_FILE_NAME = ".auto_mas_view.json"
FINGERPRINT_IGNORED_FILES = frozenset({"config/maa_option.json", VIEW_MARKER_FILE_NAME})
# 已知的运行期状态文件（项目相对 posix，小写）：runner 每轮重写的 maa_option.json、M9A agent
# 原地写的账号记录与仓库快照、热更新的清单缓存。用户导入的多半是自己一直在用的目录，里面
# 早有这些文件；它们不属于任何版本：采纳时不进载荷，切换版本时视图里有就按视图私有文件
# 原样带过去——按受管文件处理的话，换版本会把它们换回导入那一刻的内容（更新包从旧载荷
# 继承了它），或当成「新版本删掉的文件」丢掉。
RUNTIME_STATE_FILES = frozenset(
    {
        "config/maa_option.json",
        "config/m9a_data.json",
        "config/warehouse_inventory.json",
        "data/manifest_cache.json",
    }
)
# 上面这些里随版本走的一部分：M9A 热更新的清单缓存与随版本发布的 data/ 表成对，缓存里的时间戳
# 说明「数据已经更新到哪」。换到另一个载荷时 data/ 取新载荷，缓存也只能取新载荷那份（新载荷
# 没有就不要，M9A 下次全量检查）；带视图这份会让缓存比数据新，热更新一直走快速路径跳过。
# 同一载荷上重建视图（采纳、修复）时数据没变，照常按运行期状态带过去。
VERSION_BOUND_STATE_FILES = frozenset({"data/manifest_cache.json"})

# 受管项目跑起来时，runner 会往 <项目>/maafw/ 铺一层共享的 MaaFramework 原生运行时，
# 并留下这个标记文件。带标记的 maafw/ 是运行期产物，同样要排除；没有标记的 maafw/ 是
# 发行包自带的，必须照常算进指纹。
NATIVE_RUNTIME_OVERLAY_DIR = "maafw"
NATIVE_RUNTIME_OVERLAY_MARKER = ".auto_mas_maafw_native_runtime.json"


def artifact_id_for(
    source: str,
    version: str,
    download_url: str,
    *,
    explicit: str | None = None,
    asset_name: str = "",
) -> str:
    """Build a stable identity that does not depend on signed URL queries."""

    value = str(explicit or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{24}", value):
        return value
    parsed_name = Path(download_url.split("?", 1)[0].split("#", 1)[0]).name
    identity = "\0".join(
        (
            str(source or "").strip().casefold(),
            str(version or "").strip(),
            str(asset_name or parsed_name).strip().casefold(),
        )
    )
    if value:
        identity += f"\0{value}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def normalise_sha256(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[7:].strip()
    if len(raw) != 64 or any(char not in "0123456789abcdef" for char in raw):
        return None
    return raw


def project_fingerprint(project_path: str | Path) -> str | None:
    """Hash project inputs while excluding updater-owned working files."""

    root = Path(project_path).expanduser().resolve(strict=False)
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    ignored_dirs = set(FINGERPRINT_IGNORED_DIRS)
    if (root / NATIVE_RUNTIME_OVERLAY_DIR / NATIVE_RUNTIME_OVERLAY_MARKER).is_file():
        ignored_dirs.add(NATIVE_RUNTIME_OVERLAY_DIR)
    # 相对路径直接从字符串前缀切出来，每个候选只算一次：以前扫描、排序键、写摘要各做一次
    # relative_to，上万文件的项目（MaaFgo）光这一项就要好几秒。rglob 给的路径都是 root
    # 拼出来的，前缀必然一致；万一不一致按原逻辑跳过。
    root_prefix = str(root).rstrip("\\/") + os.sep
    files: list[tuple[str, Path]] = []
    for candidate in root.rglob("*"):
        text = str(candidate)
        if not text.startswith(root_prefix):
            continue
        relative = text[len(root_prefix) :].replace(os.sep, "/")
        parts = relative.split("/")
        if any(part in RESERVED_PROJECT_DIRS for part in parts):
            continue
        if any(part in ignored_dirs for part in parts):
            continue
        if relative.casefold() in FINGERPRINT_IGNORED_FILES:
            continue
        if candidate.is_symlink():
            return None
        if candidate.is_file():
            files.append((relative, candidate))
    for relative, candidate in sorted(files, key=lambda item: item[0].casefold()):
        try:
            content = candidate.read_bytes()
        except OSError:
            return None
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def safe_relative_path(raw_path: str) -> str:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    candidate = Path(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or candidate.drive
        or candidate.root
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError(f"update package contains unsafe path: {raw_path}")
    if candidate.parts[0] in RESERVED_PROJECT_DIRS:
        raise ValueError(f"update package cannot write to reserved path: {raw_path}")
    return candidate.as_posix()


__all__ = [
    "ArtifactType",
    "FINGERPRINT_IGNORED_DIRS",
    "FINGERPRINT_IGNORED_FILES",
    "NATIVE_RUNTIME_OVERLAY_DIR",
    "NATIVE_RUNTIME_OVERLAY_MARKER",
    "RESERVED_PROJECT_DIRS",
    "VIEW_MARKER_FILE_NAME",
    "artifact_id_for",
    "canonical_json",
    "is_within",
    "normalise_sha256",
    "project_fingerprint",
    "safe_relative_path",
]
