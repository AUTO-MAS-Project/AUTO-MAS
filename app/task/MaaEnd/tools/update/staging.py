#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""暂存目录与它的跨轮续传状态。

`_mas_endfield_update/state.json` 是续传的唯一事实来源：记着这一轮是为哪个本地版本、取哪个
目标版本、各卷的指纹，以及有没有开始覆盖游戏文件。缺它、坏它、或它与本轮差量对不上，一律按
没有暂存处理。只有本轮完成、服务端换了目标或指纹、以及超过 `_STAGING_RETENTION_SECONDS`
没动过，才把暂存整个清掉；取消、超时、失败、门禁拦住都留着给下一轮。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.utils.io import force_rmtree
from app.utils.update_files import file_md5, file_size, native_path, replace_file

from .common import _HALF_LANDED_MESSAGE, EndfieldUpdateError, Release, logger
from .protocol import _safe_file_name

_STAGING_DIR_NAME = "_mas_endfield_update"
"""差量分卷暂存目录，放在安装目录内：几 GB 的差量往常年在 C 盘的 MAS 数据目录里塞会
撞上系统盘余量，且同卷才能让落盘的最后一步是原子改名。"""

_STATE_NAME = "state.json"
"""暂存目录里的续传状态，跨轮保留的唯一事实来源。

记下这一轮是为哪个本地版本、取哪个目标版本、各卷的指纹，以及有没有开始覆盖游戏文件。
刻意不以 `.mas-part` 结尾：那个后缀是 `_collect_temp_files` 的清扫口径，状态文件不能被
当成孤儿残骸删掉。
"""

_STAGING_RETENTION_SECONDS = 14 * 24 * 3600
"""暂存的保留上界（14 天）。续传本身不该有期限，但用户改用启动器更新完就不回来的那些
分卷会一直在游戏目录所在分区里占几 GB，得有个尽头。"""


@dataclass(frozen=True)
class StagingState:
    """暂存目录里的续传状态：上一轮下到哪儿、有没有开始覆盖游戏文件。

    它是跨轮续传的唯一事实来源。缺了它，暂存里那些分卷只是来历不明的残骸，一律当没有。
    """

    request_version: str
    """上一轮上报的本地版本原文；换了一轮基线就不再复用。"""
    target_version: str
    """上一轮的目标版本原文；服务端换了目标就不再复用。"""
    parts: tuple[tuple[int, str, int, str], ...]
    """各卷的 `(ordinal, 落盘名, 体积, md5)`，按清单顺序；指纹变了就不再复用。"""
    landing_started: bool = False
    """是否已经动过游戏目录：真值表示客户端可能停在半新半旧。"""
    updated_at: float = 0.0
    """最后写入时刻（epoch 秒），用来给残留设一个尽头。"""


def _state_path(staging: Path) -> Path:
    return staging / _STATE_NAME


def parts_fingerprint(release: Release) -> tuple[tuple[int, int, str], ...]:
    """差量本身的指纹：序位、体积与 md5。落盘名不参与——名字随 URL 变，内容才作数。"""

    return tuple((part.ordinal, part.size, part.md5) for part in release.parts)


def read_staging_state(staging: Path) -> StagingState | None:
    """读续传状态；缺失、读不出或结构不对一律返回 `None`（按「没有状态」处理）。

    这里绝不抛：状态文件坏掉只该让本轮退回「从头下」，不该打死一次更新。
    """

    try:
        doc = json.loads(_state_path(staging).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    raw_parts = doc.get("parts")
    if not isinstance(raw_parts, list):
        return None
    parts: list[tuple[int, str, int, str]] = []
    for item in raw_parts:
        if not isinstance(item, dict):
            return None
        try:
            parts.append(
                (
                    int(item["ordinal"]),
                    str(item["name"]),
                    int(item["size"]),
                    str(item["md5"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            return None
    try:
        updated_at = float(doc.get("updated_at") or 0.0)
    except (TypeError, ValueError):
        updated_at = 0.0
    return StagingState(
        request_version=str(doc.get("request_version") or ""),
        target_version=str(doc.get("target_version") or ""),
        parts=tuple(parts),
        landing_started=bool(doc.get("landing_started")),
        updated_at=updated_at,
    )


def write_staging_state(staging: Path, state: StagingState) -> None:
    """原子落盘续传状态；写不进去只记一行日志，绝不让状态维护打死一轮更新。"""

    doc = {
        "request_version": state.request_version,
        "target_version": state.target_version,
        "parts": [
            {"ordinal": ordinal, "name": name, "size": size, "md5": md5}
            for ordinal, name, size, md5 in state.parts
        ],
        "landing_started": state.landing_started,
        "updated_at": state.updated_at,
    }
    target = _state_path(staging)
    temp = target.with_name(_STATE_NAME + ".tmp")
    try:
        staging.mkdir(parents=True, exist_ok=True)
        temp.write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        os.replace(native_path(temp), native_path(target))
    except OSError as error:
        logger.warning(f"未能写入续传状态 {target}：{error}")


def _state_for_release(
    staging: Path, state: StagingState, release: Release, *, now: float
) -> StagingState | None:
    """判断这份状态还能不能用来续传；能就把时刻续上并返回它，不能就返回 `None`。

    「不能」的四种情形都退回从头下：没有状态、目标版本换了、差量指纹换了、放太久了。
    目标版本或指纹变化说明服务端重出了一轮，混两轮的分卷拼起来的包是坏的。
    """

    if state is None:
        return None
    if state.target_version != release.version:
        logger.info(
            f"续传状态记的是目标 {state.target_version or '未知'}，"
            f"本轮目标是 {release.version}，暂存作废"
        )
        return None
    if tuple(
        (ordinal, size, md5) for ordinal, _name, size, md5 in state.parts
    ) != parts_fingerprint(release):
        logger.info("续传状态记的差量指纹与本轮不符，暂存作废")
        return None
    if now - state.updated_at > _STAGING_RETENTION_SECONDS:
        logger.info(
            f"续传状态已有 {(now - state.updated_at) / 86400:.0f} 天没动过，暂存作废"
        )
        return None
    fresh = StagingState(
        request_version=state.request_version,
        target_version=state.target_version,
        parts=state.parts,
        landing_started=state.landing_started,
        updated_at=now,
    )
    write_staging_state(staging, fresh)
    return fresh


async def _reusable_parts(
    staging: Path, state: StagingState, release: Release, names: Sequence[str]
) -> tuple[tuple[Path | None, ...], int]:
    """按状态认出还能复用的分卷，顺带把它们对齐成当前清单的落盘名。

    只认体积与 md5 都对得上的；名字对不上时按 `ordinal` 找同一卷的另一个名字——CDN 换过
    路径名不该让已下好的几 GB 白费。返回与 `release.parts` 对齐的槽位，以及复用到的字节数。
    """

    recorded = {ordinal: name for ordinal, name, _size, _md5 in state.parts}
    slots: list[Path | None] = []
    reused = 0
    for index, part in enumerate(release.parts):
        name = names[index]
        if not name:
            # 名字都认不出来就无从对齐，留给下载环节去报那个错
            slots.append(None)
            continue
        target = staging / name
        candidates = [target]
        other = recorded.get(part.ordinal)
        if other and other != name:
            candidates.append(staging / other)
        found: Path | None = None
        for candidate in candidates:
            if file_size(candidate) != part.size:
                continue
            if part.md5:
                try:
                    digest = await asyncio.to_thread(file_md5, candidate)
                except OSError as error:
                    # 读不动（被占用、权限）只说明这一卷这次认不出来，不打断整轮更新
                    logger.warning(
                        f"暂存里的 {candidate.name} 读不动，按未下好处理：{error}"
                    )
                    continue
                if digest != part.md5:
                    logger.warning(
                        f"暂存里的 {candidate.name} 指纹不符，不当作已下好的一卷"
                    )
                    continue
            found = candidate
            break
        if found is None:
            slots.append(None)
            continue
        if found != target:
            try:
                replace_file(found, target, clear_readonly=True)
            except OSError as error:
                logger.warning(f"未能把复用的分卷 {found.name} 改名为 {name}：{error}")
                slots.append(None)
                continue
            found = target
        logger.info(f"复用上轮已下好的分卷: {target.name}")
        reused += part.size
        slots.append(found)
    return tuple(slots), reused


class _Staging:
    """一轮更新对暂存目录的用法：能续的留着，动手之前记下标记，收尾决定清不清。

    把「这份暂存还算不算数」集中在 `prepare` 一处判定，其余各步只问它要结果。
    """

    def __init__(
        self, install_dir: Path, release: Release, request_version: str
    ) -> None:
        self.path = install_dir / _STAGING_DIR_NAME
        self._release = release
        self._request_version = request_version
        self._state: StagingState | None = None
        self.reusable: tuple[Path | None, ...] = ()
        self.reused_bytes = 0
        # 分卷落盘名在这里只用来认盘上已有的文件，认不出就留空让这一卷重下；真正的
        # 「名字不可用就整轮判废」仍由 `_download_release` 负责，那道门不能松
        self._names: tuple[str, ...] = tuple(
            _safe_file_name(part.url) for part in release.parts
        )

    @property
    def landing_started(self) -> bool:
        """上一轮或本轮是否已经动过游戏目录。"""

        return bool(self._state and self._state.landing_started)

    def prepare(self) -> None:
        """读状态决定清不清：不能续的（没有状态、换了目标、指纹变了、放太久）整体清掉重建。

        清理必须排在磁盘门之前：上一轮删不动的残卷压着同一分区的 free，先判后清就每轮
        都是「放不下」，而那一轮根本走不到清理。
        """

        self._clear_obstruction()
        state = _state_for_release(
            self.path, read_staging_state(self.path), self._release, now=time.time()
        )
        if state is None:
            force_rmtree(self.path)
            if self.path.exists():
                logger.warning(
                    f"未能清除上轮暂存 {self.path}，它占的还要算进本轮磁盘余量"
                )
            state = StagingState(
                request_version=self._request_version,
                target_version=self._release.version,
                parts=tuple(
                    (part.ordinal, self._names[index], part.size, part.md5)
                    for index, part in enumerate(self._release.parts)
                ),
                updated_at=time.time(),
            )
            self._state = state
            write_staging_state(self.path, state)
        else:
            self._state = state
        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            # 到这儿说明这个位置既清不掉也建不起来（被别的进程占着、盘只读）。给一句
            # 看得懂的话，别让 FileExistsError 一路落到「MAS 自动更新失败」那种笼统结论
            raise EndfieldUpdateError(
                f"无法准备暂存目录 {self.path}：{error}；请关闭占用该路径的程序后重试"
            ) from error

    def _clear_obstruction(self) -> None:
        """清掉占着暂存路径的那个同名文件。

        暂存名是 MAS 自己独占的，正常它只能是目录；真躺着一个同名文件时 `force_rmtree`
        删不动它（它只处理目录树），后面的 `mkdir` 与 `iterdir` 会接连炸掉，而 `iterdir`
        那一下是在 `finally` 里抛的，会直接逃出「对外承诺不抛异常」。
        """

        if not self.path.is_file():
            return
        logger.warning(f"暂存位置 {self.path} 被一个同名文件占用，先清掉它")
        try:
            self.path.unlink()
        except OSError as error:
            raise EndfieldUpdateError(
                f"暂存位置 {self.path} 被同名文件占用且清不掉：{error}；"
                "请手动删除该文件后重试"
            ) from error

    async def claim_reusable(self) -> int:
        """认出能复用的分卷并返回复用到的字节数（状态不可信时是 0）。"""

        if self._state is None:
            return 0
        self.reusable, self.reused_bytes = await _reusable_parts(
            self.path, self._state, self._release, self._names
        )
        return self.reused_bytes

    def mark_landing_started(self) -> None:
        """第一次往游戏目录里写之前置位，幂等。

        它只在这一刻置位是有讲究的：下载与核对阶段一个字都没写进游戏目录，那时置位会
        让下一轮把「什么都没动过」误判成「半新半旧」，白白阻断用户的任务。
        """

        if self._state is None or self._state.landing_started:
            return
        self._state = StagingState(
            request_version=self._state.request_version,
            target_version=self._state.target_version,
            parts=self._state.parts,
            landing_started=True,
            updated_at=time.time(),
        )
        write_staging_state(self.path, self._state)

    def finish(self, *, completed: bool) -> None:
        """收尾：完成了就清干净，没完成就留着给下一轮续传。

        这里跑在 `finally` 里，所以绝不能抛：真抛出去就绕过了「对外承诺不抛异常」，
        调用方拿不到结论、只能看见一个笼统的任务失败。
        """

        try:
            if completed or self._state is None:
                force_rmtree(self.path)
                return
            if self._state.landing_started:
                logger.info("已保留落了一半的现场与已下载的分卷，下一轮接着完成")
            elif self._has_partial_download():
                logger.info("已保留已下载的分卷，下一轮接着下")
            else:
                # 盘上一个字节都没下成：留一个空目录加状态没有意义，下一轮还会从头来
                force_rmtree(self.path)
        except OSError as error:
            logger.warning(f"收尾清理暂存 {self.path} 失败，留给下一轮再清：{error}")

    def _has_partial_download(self) -> bool:
        """暂存里除了状态文件还有别的吗。

        判据不能只看最终分卷名：下到一半的那卷是以 `.mas-part` 名字躺在这里的，只认
        最终名会把几个 GB 的进度当成没有而下令清掉。
        """

        if not self.path.is_dir():
            # 不是目录（位置被占、或压根不存在）就没有「已下载的分卷」可言
            return False
        return any(entry.name != _STATE_NAME for entry in self.path.iterdir())


def _residual_state(install_dir: Path) -> StagingState | None:
    """读一次上一轮留在暂存目录里的状态；没有就是没有。"""

    return read_staging_state(install_dir / _STAGING_DIR_NAME)


def _clear_residual(install_dir: Path) -> None:
    """客户端已经不需要这份暂存了（已是目标版本、或已不是当初那个客户端）就清干净。"""

    force_rmtree(install_dir / _STAGING_DIR_NAME)


def _half_landed_block(residual: StagingState | None) -> str | None:
    """上一轮已经动过游戏目录时，本轮判不了就不放行。"""

    return (
        _HALF_LANDED_MESSAGE
        if residual is not None and residual.landing_started
        else None
    )
