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

"""运行前更新的「预检备忘」闸门：上次装不上的版本，这次先轻探再决定要不要更新。

更新事务在提交前真建运行环境（``tools/embedded/precheck.py``），建不出来就回滚
并写一份备忘（``precheck_memo.py``）。之后每次运行前更新走到「确认有新版本」
那一步时，核心包会 await 这里构造的闸门：

- 没备忘、或备忘记的不是这个目标版本 → 放行（正常更新，预检再真建一次）。
- ``kind == other``（磁盘满、解释器坏……）→ 不探，计数，跳过本次更新。
- ``kind == binding_unavailable`` → 并发轻探 PyPI 各索引的 simple 页与 GitHub
  的 tag 源码包（5 s、只看有没有），任一可得就删备忘放行；都不可得就计数、
  跳过——不下载、不解压、不建池、不弹通知。

只有运行前自动更新用它；手动更新不传闸门，等于强制重试。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.task.MaaFW.tools.core.automas_maafw_project_update.precheck_memo import (
    KIND_BINDING_UNAVAILABLE,
    clear_runtime_precheck,
    memo_matches_version,
    read_runtime_precheck,
    write_runtime_precheck,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.binding_fallback import (
    pep440_to_maafw_tag,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.installer import (
    is_package_index_offline,
    resolve_package_index_candidates,
)
from app.utils import get_logger

logger = get_logger("MFW 预检备忘")

# tag 源码包的唯一真实来源；``github.com/…/archive/…`` 对任何 tag（含不存在的）
# 都无条件 302 到这里，探它得不到「有没有」的答案。
MAAFW_CODELOAD_URL = (
    "https://codeload.github.com/MaaXYZ/MaaFramework/zip/refs/tags/{tag}"
)
DEFAULT_PACKAGE_INDEX = "https://pypi.org/simple/"
PROBE_TIMEOUT_SECONDS = 5.0
PROBE_HEADERS = {"User-Agent": "AutoMasGui"}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_REASON_SUMMARY_CHARS = 120

PrecheckGate = Callable[[str], Awaitable[str | None]]
BindingProbe = Callable[[str], Awaitable[bool]]


def maafw_git_tag_for(version_text: str) -> str | None:
    """PEP 440 版本号 → MaaFramework 的 git tag；映射不出来返回 None。

    与兜底打包用的是同一份规则（``runtime_pool/binding_fallback.pep440_to_maafw_tag``），
    这里只是宿主侧的别名，免得轻探探的 tag 和兜底下载的 tag 各算各的。
    """

    return pep440_to_maafw_tag(version_text)


def exact_maafw_version(requirement_text: str | None) -> str | None:
    """``maafw==5.14.0b1`` → ``5.14.0b1``（规范化）；不是精确钉版本就返回 None。"""

    try:
        requirement = Requirement(str(requirement_text or "").strip())
    except InvalidRequirement:
        return None
    if canonicalize_name(requirement.name) != "maafw":
        return None
    specs = list(requirement.specifier)
    if len(specs) != 1 or specs[0].operator != "==":
        return None
    try:
        return str(Version(specs[0].version))
    except InvalidVersion:
        return None


def _is_loopback_index(url: str) -> bool:
    try:
        host = (urlsplit(str(url)).hostname or "").strip().casefold()
    except ValueError:
        return False
    return host in _LOOPBACK_HOSTS


async def _probe_index(client: httpx.AsyncClient, index_url: str, marker: str) -> bool:
    response = await client.get(f"{str(index_url).rstrip('/')}/maafw/")
    if response.status_code != 200:
        return False
    return marker in response.text.casefold()


async def _probe_codeload(client: httpx.AsyncClient, tag: str) -> bool:
    response = await client.head(MAAFW_CODELOAD_URL.format(tag=tag))
    return response.status_code == 200


async def probe_binding_available(
    version_text: str,
    *,
    proxy: httpx.Proxy | None = None,
    index_candidates: Sequence[str] | None = None,
    offline: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> bool:
    """这个版本的 maafw binding 现在拿不拿得到（只看有没有，不下载）。

    并发探：每个非回环索引的 ``<index>/maafw/`` simple 页里找
    ``maafw-<X>-``（ustc 会 301，所以跟跳转）；GitHub 只 HEAD codeload 的 tag
    源码包、只有 200 算可得（不存在回 404）。离线模式整个跳过、视为不可得。
    回环中继（Runtime 的 ``127.0.0.1:<port>``）不探：它只是转发上游镜像。
    ``index_candidates`` 为 None（未受监督）时探 pypi.org。
    """

    if offline:
        return False
    try:
        normalized = str(Version(str(version_text or "").strip()))
    except InvalidVersion:
        return False
    marker = f"maafw-{normalized}-".casefold()
    candidates = (
        [DEFAULT_PACKAGE_INDEX] if index_candidates is None else list(index_candidates)
    )
    indexes = [
        candidate
        for candidate in candidates
        if str(candidate or "").strip() and not _is_loopback_index(candidate)
    ]
    tag = maafw_git_tag_for(normalized)

    client_kwargs: dict[str, object] = {
        "timeout": httpx.Timeout(timeout),
        "follow_redirects": True,
        "headers": PROBE_HEADERS,
    }
    if transport is not None:
        client_kwargs["transport"] = transport
    else:
        client_kwargs["proxy"] = proxy
    async with httpx.AsyncClient(**client_kwargs) as client:  # type: ignore[arg-type]
        probes: list[Awaitable[bool]] = [
            _probe_index(client, index_url, marker) for index_url in indexes
        ]
        if tag is not None:
            probes.append(_probe_codeload(client, tag))
        if not probes:
            return False
        results = await asyncio.gather(*probes, return_exceptions=True)
    return any(result is True for result in results)


def _next_attempts(memo: dict) -> int:
    try:
        return max(0, int(memo.get("attempts") or 0)) + 1
    except (TypeError, ValueError):
        return 1


def _summarize_reason(reason: object) -> str:
    text = str(reason or "").strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) > _REASON_SUMMARY_CHARS:
        return first_line[: _REASON_SUMMARY_CHARS - 1] + "…"
    return first_line or "无原因"


def build_precheck_gate(
    project_path: str | Path,
    *,
    project_name: str | None = None,
    proxy: httpx.Proxy | None = None,
    send_log: Callable[[str], None] | None = None,
    operation_root: Path | None = None,
    probe: BindingProbe | None = None,
) -> PrecheckGate:
    """构造给 ``update_maafw_project_if_needed(precheck_gate=...)`` 的闸门。

    返回值非空即「本次跳过更新」的原因，由核心包按「有更新但不可安装」记
    日志并返回 ``skipped_reason``（这里不再重复记同一句）。``probe`` 只给
    测试替换轻探；生产用 :func:`probe_binding_available` 加 Runtime 注入的
    索引候选与离线判据。
    """

    root = Path(project_path)
    log = send_log or (lambda _message: None)
    name = str(project_name or "").strip() or "MFW 项目"

    async def run_probe(version: str) -> bool:
        if probe is not None:
            return bool(await probe(version))
        return await probe_binding_available(
            version,
            proxy=proxy,
            index_candidates=resolve_package_index_candidates(),
            offline=is_package_index_offline(),
        )

    async def gate(latest: str) -> str | None:
        memo = await asyncio.to_thread(
            read_runtime_precheck, root, operation_root=operation_root
        )
        if memo is None:
            return None
        if not memo_matches_version(memo, latest):
            await asyncio.to_thread(
                clear_runtime_precheck, root, operation_root=operation_root
            )
            log(
                f"上次运行环境预检失败记的是 {memo.get('targetVersion')}，"
                f"目标版本已变为 {latest}，重新尝试更新"
            )
            return None

        attempts = _next_attempts(memo)
        requirement = str(memo.get("requirement") or "maafw").strip() or "maafw"
        if memo.get("kind") != KIND_BINDING_UNAVAILABLE:
            memo["attempts"] = attempts
            await asyncio.to_thread(
                write_runtime_precheck, root, memo, operation_root=operation_root
            )
            return (
                f"上次对 {latest} 的运行环境预检失败"
                f"（{_summarize_reason(memo.get('reason'))}），"
                f"本次不再自动重试（第 {attempts} 次）；手动更新可强制重试"
            )

        version = exact_maafw_version(requirement)
        available = False
        if version is not None:
            try:
                available = await run_probe(version)
            except Exception as exc:  # noqa: BLE001 - 轻探失败按不可得处理
                logger.warning(f"轻探 maafw {version} 是否可得时出错：{exc}")
                available = False
        if available:
            await asyncio.to_thread(
                clear_runtime_precheck, root, operation_root=operation_root
            )
            log(f"maafw {version} 现已可得，重新尝试更新 {latest}")
            return None

        memo["attempts"] = attempts
        await asyncio.to_thread(
            write_runtime_precheck, root, memo, operation_root=operation_root
        )
        needed = f"maafw {version}" if version else requirement
        return (
            f"{name} {latest} 需要 {needed}，"
            f"PyPI/GitHub 仍不可得，本次不升级（第 {attempts} 次）"
        )

    return gate


__all__ = [
    "DEFAULT_PACKAGE_INDEX",
    "MAAFW_CODELOAD_URL",
    "PROBE_TIMEOUT_SECONDS",
    "build_precheck_gate",
    "exact_maafw_version",
    "maafw_git_tag_for",
    "probe_binding_available",
]
