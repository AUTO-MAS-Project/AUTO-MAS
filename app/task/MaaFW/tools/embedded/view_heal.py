#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""运行前把旧投影规则漏装的 agent 代码文件补进视图（每个视图只查一次）。

v5.6.0 的投影逐级匹配目录名，把 MaaFgo v2.0.03 的 ``agent/battle/runtime/`` 当成外壳剔掉，
agent 一起来就 ``ModuleNotFoundError``。规则修好（#1104）之后，已经建好的载荷与视图不会
自己恢复。这里只做用户手动能做的那一步：找出新规则会保留、视图里却没有的**代码文件**
（只看 agent / 依赖目录，``projection._code_roots``），从发行包里取出来直接写进视图——
效果与用户自己拷进去一样：它们是视图私有文件，换版本时照常带过去，新载荷里有同路径
文件时以载荷为准。不重建载荷、不动登记与更新流程。

比对依据按代价从低到高：本地导入且来源目录还是同一版本 → 来源目录；更新包下载缓存里有
同版本的完整包 → 本地 zip；都没有才读 GitHub Release 资产：包一层只读、可 seek 的
:class:`RangeHTTPReader` 交给标准库 ``zipfile``，读中央目录与缺的条目时才按 64 KB 对齐
发 HTTP Range，解析、解压、CRC 校验全在标准库里。Mirror 酱的一次性签名地址不碰；GitHub
CDN 不认后缀式 Range（``bytes=-N`` 回 501），总大小用 ``bytes=0-0`` 的 Content-Range 拿；
服务端回 200 全量时不读响应体，直接放弃。**不下载整包。**

结果记进视图标记 ``.auto_mas_view.json`` 的 ``projectionHeal``（与 ``envConfirmedFor``
同一种写法：临时文件 + ``os.replace``，其余字段不动）；视图换到别的载荷后标记整个换掉，
新视图再查一次。失败不挡运行，只记一行日志；拿不到比对依据这类暂时性失败最多试
``MAX_ATTEMPTS`` 次。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import zipfile
import zlib
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import httpx
import json5

from app.task.MaaFW.tools.core.project_update import payloads
from app.task.MaaFW.tools.core.project_update.apply import _EntryBoundary
from app.task.MaaFW.tools.core.project_update.projection import (
    CODE_FILE_SUFFIXES,
    ProjectionError,
    ProjectionRules,
    _code_roots,
    _is_relative_to,
    build_projection_rules,
)
from app.task.MaaFW.tools.core.project_update.state import DEFAULT_CACHE_ROOT
from app.task.MaaFW.tools.core.project_update.timing import format_duration
from app.task.MaaFW.tools.embedded.embedded_project import (
    VIEW_MARKER_NAME,
    embedded_project_dir,
    payloads_root,
    read_view_marker,
)
from app.utils import get_logger

logger = get_logger("MFW 视图补齐")

HEAL_FIELD = "projectionHeal"
# 投影规则改一次加一：比这个旧的检查结果作废、再查一次。1 = #1104「目录名只在顶层算数」。
HEAL_REVISION = 1
# 暂时性失败（断网、GitHub 连不上）最多试几次；拿不到依据的永久原因只记一次。
MAX_ATTEMPTS = 3
# 远端按这么大的块对齐读、缓存：zipfile 的多次小读取落在同一块里就不再发请求。
RANGE_BLOCK_SIZE = 64 * 1024
# 一次最多从远端读这么多（中央目录 + 缺的条目）：MaaFgo 一万多条目的中央目录 1.6 MB。
MAX_REMOTE_BYTES = 64 * 1024 * 1024
HTTP_TIMEOUT = httpx.Timeout(20.0, connect=8.0)
HTTP_HEADERS = {"User-Agent": "AutoMasGui"}
_INTERFACE_NAMES = ("interface.json", "interface.jsonc")
_ZIP_ENTRY_LIMIT = 100_000
_LOG_ITEMS = 3


class HealSkip(RuntimeError):
    """拿不到比对依据或条目不能用；``permanent`` 的不再重试。"""

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


# --------------------------------------------------------------------------
# 远端：按区间读取的只读文件对象，交给 zipfile
# --------------------------------------------------------------------------


def _parse_content_range(value: str) -> tuple[int, int, int | None] | None:
    from app.task.MaaFW.tools.core.project_update.transport import (
        _parse_content_range as parse,
    )

    return parse(value)


class RangeHTTPReader:
    """只读、可 seek 的远端文件：``read`` 时按 ``block_size`` 对齐发 HTTP Range，读过的块
    缓存起来。只接受与请求一致的 206（回 200 时不读响应体、直接放弃），累计读到
    ``max_bytes`` 就停。"""

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        *,
        expected_size: int | None = None,
        block_size: int = RANGE_BLOCK_SIZE,
        max_bytes: int = MAX_REMOTE_BYTES,
    ) -> None:
        self.client = client
        self.url = url
        self.block_size = block_size
        self.max_bytes = max_bytes
        self.blocks: dict[int, bytes] = {}
        self.position = 0
        self.fetched = 0
        self.requests = 0
        self.size = 0
        # 总大小：GitHub CDN 不认 ``bytes=-N``，用 ``bytes=0-0`` 的 Content-Range。
        total = self._request(0, 0)[1]
        if not total:
            raise HealSkip("下载服务器没给出发行包大小", permanent=True)
        if expected_size and total != expected_size:
            raise HealSkip("发行包大小与 Release 记录的不同")
        self.size = total

    def _request(self, start: int, end: int) -> tuple[bytes, int | None]:
        expected = end - start + 1
        if self.fetched + expected > self.max_bytes:
            raise HealSkip("要读的太多，不在运行前自动补齐", permanent=True)
        self.requests += 1
        buffer = bytearray()
        try:
            with self.client.stream(
                "GET",
                self.url,
                headers={**HTTP_HEADERS, "Range": f"bytes={start}-{end}"},
            ) as response:
                if response.status_code != 206:
                    # 200 就是服务端不认 Range、要把整包发过来：一个字节都不读。
                    raise HealSkip(
                        f"下载服务器不支持按区间读取（HTTP {response.status_code}）",
                        permanent=response.status_code == 200,
                    )
                parsed = _parse_content_range(
                    str(response.headers.get("content-range") or "")
                )
                if (
                    parsed is None
                    or parsed[:2] != (start, end)
                    or (self.size and parsed[2] not in (None, self.size))
                ):
                    raise HealSkip("下载服务器回的区间与请求不符")
                for chunk in response.iter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > expected:
                        raise HealSkip("下载服务器回的区间比请求的长")
        except httpx.HTTPError as exc:
            raise HealSkip(f"读取发行包失败：{type(exc).__name__}") from exc
        if len(buffer) != expected:
            raise HealSkip("下载服务器回的区间不完整")
        self.fetched += expected
        return bytes(buffer), parsed[2]

    def _ensure(self, first: int, last: int) -> None:
        """把 ``[first, last]`` 里还没有的块读进来，连续缺的合成一次请求。"""

        runs: list[list[int]] = []
        for index in range(first, last + 1):
            if index in self.blocks:
                continue
            if runs and index == runs[-1][-1] + 1:
                runs[-1].append(index)
            else:
                runs.append([index])
        for run in runs:
            start = run[0] * self.block_size
            end = min(self.size, (run[-1] + 1) * self.block_size) - 1
            data = self._request(start, end)[0]
            for offset, index in enumerate(run):
                begin = offset * self.block_size
                self.blocks[index] = data[begin : begin + self.block_size]

    def read(self, size: int | None = -1) -> bytes:
        if size is None or size < 0:
            size = self.size - self.position
        end = min(self.size, self.position + size)
        if end <= self.position:
            return b""
        first = self.position // self.block_size
        last = (end - 1) // self.block_size
        self._ensure(first, last)
        joined = b"".join(self.blocks[index] for index in range(first, last + 1))
        begin = self.position - first * self.block_size
        data = joined[begin : begin + (end - self.position)]
        self.position = end
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.position, 2: self.size}.get(whence)
        if base is None or base + offset < 0:
            raise ValueError(f"invalid seek: {offset}, {whence}")
        self.position = base + offset
        return self.position

    def tell(self) -> int:
        return self.position

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def close(self) -> None:
        self.blocks.clear()


def _open_client(proxy: httpx.Proxy | None) -> httpx.Client:
    """测试替换这里注入 ``MockTransport``。"""

    return httpx.Client(proxy=proxy, follow_redirects=True, timeout=HTTP_TIMEOUT)


async def _github_asset(
    interface_model: Any, version: str, *, proxy: httpx.Proxy | None, shell_hint: str
) -> tuple[str, int]:
    """同版本 GitHub Release 发行包的地址与大小（选资产与更新同一套规则）。"""

    from app.task.MaaFW.tools.core.project_update.updater import (
        MaaFWProjectUpdateError,
        _check_github_release_update,
        _normalize_github_repo,
    )

    if interface_model is None or not _normalize_github_repo(
        str(getattr(interface_model, "github", "") or "")
    ):
        raise HealSkip("interface.json 没有声明 github 仓库", permanent=True)
    try:
        discovery = await _check_github_release_update(
            interface_model,
            current_version="",
            source_config={"project_shell_hint": shell_hint} if shell_hint else {},
            proxy=proxy,
            target_version=version,
        )
    except (MaaFWProjectUpdateError, httpx.HTTPError) as exc:
        raise HealSkip(f"查询 GitHub Release 失败：{exc}") from exc
    candidate = discovery.candidate if discovery is not None else None
    if candidate is None or not candidate.download_url:
        raise HealSkip(f"GitHub 上没有 {version} 的发行包", permanent=True)
    host = (urlsplit(str(candidate.download_url)).hostname or "").casefold()
    if host != "github.com" and not host.endswith(".github.com"):
        raise HealSkip("发行包不在 GitHub 上，不按区间读取", permanent=True)
    return str(candidate.download_url), int(candidate.size or 0)


# --------------------------------------------------------------------------
# 比对与补齐
# --------------------------------------------------------------------------


def _norm_version(value: Any) -> str:
    return str(value or "").strip().lstrip("vV")


def _parse_json(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8-sig")
    try:
        data = json.loads(text)
    except ValueError:
        data = json5.loads(text)
    if not isinstance(data, dict):
        raise ValueError("interface.json 不是对象")
    return data


def _missing_code_files(
    rules: ProjectionRules, names: Iterable[str], view: Path
) -> list[str]:
    """新规则会保留、在 agent / 依赖目录下、视图里却没有的代码文件（``names`` 与视图同一坐标）。"""

    roots = _code_roots(rules)
    missing = []
    for rel in names:
        path = Path(rel)
        if PurePosixPath(rel).suffix.casefold() not in CODE_FILE_SUFFIXES:
            continue
        if not any(_is_relative_to(path, root) for root in roots):
            continue
        if not os.path.lexists(view / rel) and rules.keeps(path):
            missing.append(rel)
    return sorted(missing)


def _from_source(
    source: Path, view: Path, version: str
) -> tuple[dict[str, bytes], int] | None:
    """本地导入且来源目录还是这个版本：直接按新规则扫它的 agent / 依赖目录。"""

    try:
        rules = build_projection_rules(source, strict=False)
        interface = next(
            rules.interface_base / name
            for name in _INTERFACE_NAMES
            if (rules.interface_base / name).is_file()
        )
        if _norm_version(_parse_json(interface.read_bytes()).get("version")) != (
            _norm_version(version)
        ):
            return None
    except (ProjectionError, StopIteration, OSError, ValueError):
        return None
    root = rules.source_root
    found: dict[str, Path] = {}
    for code_root in _code_roots(rules):
        for current, _dirs, files in os.walk(root / code_root):
            for name in files:
                relative = (Path(current) / name).relative_to(root)
                try:
                    found[rules.output_path(relative).as_posix()] = relative
                except ProjectionError:
                    continue
    view_rules = build_projection_rules(view, strict=False)
    missing = _missing_code_files(view_rules, found, view)
    return {rel: (root / found[rel]).read_bytes() for rel in missing}, 0


def _from_archive(
    archive: zipfile.ZipFile, view: Path, lineage: str, version: str
) -> dict[str, bytes]:
    """发行包（本地缓存或远端）：核对是同一项目同一版本，取出缺的代码文件。"""

    members = archive.infolist()
    if len(members) > _ZIP_ENTRY_LIMIT:
        raise HealSkip("发行包条目太多", permanent=True)
    interfaces = [
        info
        for info in members
        if not info.is_dir() and PurePosixPath(info.filename).name in _INTERFACE_NAMES
    ]
    if not interfaces:
        raise HealSkip("发行包里没有 interface.json", permanent=True)
    chosen = min(interfaces, key=lambda info: len(PurePosixPath(info.filename).parts))
    parent = PurePosixPath(chosen.filename).parent.as_posix()
    prefix = "" if parent == "." else f"{parent}/"
    try:
        data = _parse_json(archive.read(chosen))
        same = payloads.lineage_key(data) == lineage
    except (ValueError, payloads.PayloadError) as exc:
        raise HealSkip(
            f"发行包里的 interface.json 读不了：{exc}", permanent=True
        ) from exc
    if not same or _norm_version(data.get("version")) != _norm_version(version):
        raise HealSkip("发行包与本机的项目或版本对不上", permanent=True)
    infos = {
        info.filename[len(prefix) :]: info
        for info in members
        if not info.is_dir() and info.filename.startswith(prefix)
    }
    missing = _missing_code_files(
        build_projection_rules(view, strict=False), infos, view
    )
    # 路径安全与更新解压同一判据：落在视图里、不是符号链接；有一个不合格就整批不写。
    boundary = _EntryBoundary(view)
    for rel in missing:
        info = infos[rel]
        if not boundary.contains(rel) or (info.external_attr >> 16) & 0o170000 == (
            0o120000
        ):
            raise HealSkip(f"发行包里有不安全的路径：{info.filename}", permanent=True)
    contents: dict[str, bytes] = {}
    for rel in missing:
        info = infos[rel]
        try:
            with archive.open(info) as handle:
                content = handle.read(info.file_size + 1)
        except HealSkip:
            raise
        except (NotImplementedError, RuntimeError) as exc:
            # 压缩方法标准库不认识 / 加密条目：再试也一样。
            raise HealSkip(f"{rel} 无法解压：{exc}", permanent=True) from exc
        except (OSError, EOFError, zipfile.BadZipFile, zlib.error) as exc:
            # CRC 对不上之类：整批丢弃，一个都不写。
            raise HealSkip(f"{rel} 校验失败：{exc}") from exc
        if len(content) != info.file_size:
            raise HealSkip(f"{rel} 大小与中央目录不符")
        contents[rel] = content
    return contents


def _cached_packages(cache_root: Path, version: str) -> list[Path]:
    """更新包下载缓存里目标版本是 ``version`` 的完整包。"""

    found = []
    if not cache_root.is_dir():
        return found
    for directory in sorted(cache_root.iterdir()):
        try:
            meta = json.loads((directory / "artifact.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or not meta.get("complete"):
            continue
        if _norm_version(meta.get("targetVersion")) != _norm_version(version):
            continue
        candidate = Path(str(meta.get("completePath") or ""))
        if candidate.suffix.casefold() == ".zip" and candidate.is_file():
            found.append(candidate)
    return found


def _write_files(view: Path, contents: Mapping[str, bytes]) -> None:
    """写进视图：临时名 + ``os.replace``，目标已存在的（期间有人拷进来了）不动。"""

    for rel, content in contents.items():
        target = view / rel
        if os.path.lexists(target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
            os.replace(temporary, target)
        finally:
            if os.path.lexists(temporary):
                temporary.unlink()


def _record(view: Path, payload_id: str, fields: Mapping[str, Any]) -> None:
    """结果记进视图标记（标记还挂着这个载荷才记）。"""

    marker = read_view_marker(view)
    if marker is None or str(marker["payload"]) != payload_id:
        return
    previous = (
        marker.get(HEAL_FIELD) if isinstance(marker.get(HEAL_FIELD), dict) else {}
    )
    attempts = (
        int(previous.get("attempts") or 0)
        if previous.get("payload") == payload_id
        else 0
    )
    marker[HEAL_FIELD] = {
        "revision": HEAL_REVISION,
        "payload": payload_id,
        "attempts": attempts + 1,
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **dict(fields),
    }
    payloads.write_json_atomic(view / VIEW_MARKER_NAME, marker)


def heal_due(marker: Mapping[str, Any] | None) -> bool:
    """这个视图要不要（再）查一次。"""

    if marker is None:
        return False
    record = marker.get(HEAL_FIELD)
    if not isinstance(record, dict):
        return True
    if int(record.get("revision") or 0) < HEAL_REVISION:
        return True
    if str(record.get("payload") or "") != str(marker.get("payload") or ""):
        return True
    if record.get("result") in {"healed", "clean"} or record.get("permanent"):
        return False
    return int(record.get("attempts") or 0) < MAX_ATTEMPTS


def _format_size(size: int) -> str:
    return f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 2**20:.1f} MB"


async def heal_view_code_files(
    script_id: str,
    *,
    proxy: httpx.Proxy | None = None,
    shell_hint: str = "",
    send_log: Callable[[str], None] | None = None,
    base: Path | None = None,
    cache_root: Path | None = None,
) -> str | None:
    """运行前检查调用（持本视图预约）。返回结果（``healed`` / ``clean`` / ``unavailable``），
    不用查时返回 None。**从不抛异常**：失败只记一行日志，照常运行。"""

    log = send_log or (lambda _line: None)
    view = embedded_project_dir(script_id, base)
    try:
        marker = await asyncio.to_thread(read_view_marker, view)
        if not heal_due(marker):
            return None
        assert marker is not None
        lineage, payload_id = str(marker["lineage"]), str(marker["payload"])
        manifest = (
            await asyncio.to_thread(
                payloads.read_manifest, payloads_root(base), lineage, payload_id
            )
            or {}
        )
        version = str(manifest.get("version") or marker.get("version") or "")
    except Exception as exc:  # noqa: BLE001 - 读不了标记就当不用查
        logger.warning(f"MFW 视图补齐检查失败（{script_id[:8]}）：{exc}")
        return None

    started = time.monotonic()
    via, transferred = "", 0
    try:
        source = manifest.get("source") or {}
        found = None
        if str(source.get("kind") or "") == "import" and str(source.get("ref") or ""):
            found = await asyncio.to_thread(
                _from_source, Path(str(source["ref"])), view, version
            )
            via = "导入目录"
        if found is None:
            for cached in await asyncio.to_thread(
                _cached_packages, Path(cache_root or DEFAULT_CACHE_ROOT), version
            ):
                try:
                    with zipfile.ZipFile(cached) as archive:
                        contents = await asyncio.to_thread(
                            _from_archive, archive, view, lineage, version
                        )
                except (HealSkip, OSError, zipfile.BadZipFile) as exc:
                    logger.info(f"MFW 缓存包 {cached} 不能用来比对：{exc}")
                    continue
                found, via = (contents, 0), "本机缓存的发行包"
                break
        if found is None:
            from app.task.MaaFW.tools.core.interface.loader import (
                load_interface_model_cached,
            )

            try:
                model = await asyncio.to_thread(load_interface_model_cached, view)
            except Exception:  # noqa: BLE001 - 读不了就当没声明 github
                model = None
            url, size = await _github_asset(
                model, version, proxy=proxy, shell_hint=shell_hint
            )

            def remote() -> tuple[dict[str, bytes], int]:
                with _open_client(proxy) as client:
                    reader = RangeHTTPReader(client, url, expected_size=size or None)
                    try:
                        with zipfile.ZipFile(reader) as archive:  # type: ignore[arg-type]
                            return _from_archive(archive, view, lineage, version), (
                                reader.fetched
                            )
                    except zipfile.BadZipFile as exc:
                        raise HealSkip(f"发行包的中央目录读不了：{exc}") from exc

            found, via = await asyncio.to_thread(remote), "GitHub 发行包"
        contents, transferred = found
        if contents:
            await asyncio.to_thread(_write_files, view, contents)
    except Exception as exc:  # noqa: BLE001 - 失败不挡运行
        permanent = bool(getattr(exc, "permanent", False))
        reason = str(exc).strip() or type(exc).__name__
        try:
            await asyncio.to_thread(
                _record,
                view,
                payload_id,
                {
                    "result": "unavailable",
                    "permanent": permanent,
                    "reason": reason[:300],
                },
            )
        except OSError as record_error:
            logger.warning(f"MFW 视图补齐结果写不进标记：{record_error}")
        message = f"检查 {version} 是否漏装文件没做成（{reason}），本次照常运行"
        logger.info(f"MFW 视图 {view.name}：{message}")
        if not permanent:
            # 暂时性的（断网、校验失败）才告诉用户，最多 MAX_ATTEMPTS 次；没有 GitHub
            # 仓库、服务端不认 Range 这类查不了的只进后端日志，不给每个项目刷一行。
            log(message)
        return "unavailable"

    missing = sorted(contents)
    try:
        await asyncio.to_thread(
            _record,
            view,
            payload_id,
            {
                "result": "healed" if missing else "clean",
                "count": len(missing),
                "via": via,
            },
        )
    except OSError as exc:
        logger.warning(f"MFW 视图补齐结果写不进标记：{exc}")
    if not missing:
        logger.info(
            f"MFW 视图 {view.name} 按新投影规则核对过（{via}），没有漏装的代码文件"
        )
        return "clean"
    shown = "、".join(missing[:_LOG_ITEMS]) + (
        " 等" if len(missing) > _LOG_ITEMS else ""
    )
    size = sum(len(content) for content in contents.values())
    log(
        f"检测到 {version} 缺少 {len(missing)} 个文件（{shown}），已从{via}补齐"
        f"（{_format_size(size)}"
        + (f"，下载 {_format_size(transferred)}" if transferred else "")
        + f"），用时 {format_duration(time.monotonic() - started)}"
    )
    return "healed"


__all__ = [
    "HEAL_FIELD",
    "HealSkip",
    "RangeHTTPReader",
    "heal_due",
    "heal_view_code_files",
]
