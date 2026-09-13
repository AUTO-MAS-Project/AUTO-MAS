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


from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any

import json5
import tomli_w
import yaml

from .logger import get_logger
from .tools import decode_bytes

logger = get_logger("路径迁移")

# YAML 解析器拒绝的控制字符(除 \t \n \r): 映射为 None 即 translate 时丢弃
_INVALID_YAML_CHARS = dict.fromkeys([*range(0x20), 0x7F])

# 格式后缀 -> (dump: (dict, encoding)->bytes, load: bytes->dict)
# 若要扩展格式, 直接改此表
_CODECS: dict[str, tuple[Any, Any]] = {
    ".toml": (
        lambda d, encoding: tomli_w.dumps(d, indent=2).encode(encoding),
        lambda data: tomllib.loads(decode_bytes(data)),
    ),
    ".json": (
        lambda d, encoding: json.dumps(d, ensure_ascii=False, indent=2).encode(
            encoding
        ),
        lambda data: json.loads(decode_bytes(data)),
    ),
    ".json5": (
        lambda d, encoding: json5.dumps(d, indent=2).encode(encoding),
        lambda data: json5.loads(decode_bytes(data)),
    ),
    ".jsonl": (
        lambda d, encoding: (
            "\n".join(json.dumps(i, ensure_ascii=False) for i in d).encode(encoding)
            + b"\n"
        ),
        lambda data: [
            json.loads(d) for d in decode_bytes(data).splitlines() if d.strip()
        ],
    ),
    ".yaml": (
        lambda d, encoding: yaml.safe_dump(
            d, allow_unicode=True, sort_keys=False
        ).encode(encoding),
        lambda data: yaml.safe_load(decode_bytes(data)),
    ),
    ".sanitized.yaml": (
        lambda d, encoding: yaml.safe_dump(
            d, allow_unicode=True, sort_keys=False
        ).encode(encoding),
        # 容错读: 非原子写落盘的文件可能留下 NUL 填充, YAML 解析器遇到直接抛
        # ReaderError; 只取已知字段的调用方不应因此整个失败
        lambda data: yaml.safe_load(decode_bytes(data).translate(_INVALID_YAML_CHARS)),
    ),
}

# 后缀别名, 共享同一序列化器: 别名后缀 -> 规范化后缀
# 查找时先归一化再查 _CODECS
_ALIASES: dict[str, str] = {
    ".jsonc": ".json5",
    ".yml": ".yaml",
}

# 进程内串行锁, 避免并发竞争写
_WRITE_LOCK = threading.Lock()

# 删除重试: 任务收尾复原紧跟脚本进程结束, 等被占用的句柄释放
_RMTREE_RETRIES = 5
_RMTREE_RETRY_INTERVAL = 0.3


def remove_readonly(func: Any, target: Any, _exc: BaseException) -> None:
    """``shutil.rmtree`` 的 ``onexc`` 回调: 删到只读条目时清除只读位再重试

    Windows 上 ``rmtree`` 删不掉只读文件; 清除只读位后仍失败的条目按原
    ``ignore_errors`` 语义忽略, 不向上抛出。

    Args:
        func: ``shutil`` 传入的删除函数。
        target: 删除失败的目标路径。
        _exc: ``shutil`` 传入的异常, 不使用。
    """
    with suppress(OSError):
        os.chmod(target, stat.S_IWRITE)
        func(target)


def force_rmtree(path: Path) -> None:
    """
    删除目录树, 遇到只读文件先清除只读位再重试

    ``shutil.rmtree(..., ignore_errors=True)`` 在 Windows 上删不掉只读文件且静默
    跳过, 残留文件会让随后的 ``copytree(..., dirs_exist_ok=True)`` 覆盖时抛
    ``PermissionError``; 脚本配置目录里的 ``.git`` 对象正是只读的。清除只读位后仍
    删不掉的条目按原 ``ignore_errors`` 语义忽略, 不向上抛出。

    删除**带重试**: 目标下仍有被进程占用的文件时, ``rmtree`` 会删掉能删的、
    留下被占用的, 调用方随后 ``copytree`` 或 ``rename`` 都会失败。任务收尾复原
    紧跟在脚本进程被结束后, 句柄释放存在竞态, 重试是等它释放。

    Args:
        path: 待删除的目录路径
    """

    for attempt in range(_RMTREE_RETRIES):
        try:
            shutil.rmtree(path, onexc=remove_readonly)
            return
        except OSError:
            if attempt == _RMTREE_RETRIES - 1:
                return
            sleep(_RMTREE_RETRY_INTERVAL)


def replace_dir(src: Path, dst: Path) -> None:
    """
    用 ``src`` 整目录替换 ``dst``（先清后拷, 不做改名的双份拷贝）

    只删一次且用 ``force_rmtree``: 目录带只读文件（如脚本自带的 ``.git`` 对象）
    或删除前仍有残留时都能清干净, 不需要先拷到 .tmp 再改名的中间副本——
    改名在 Windows 上并不原子, 目标存在时直接失败, 失败还会把用户的配置
    留在半删状态。

    删不掉的条目按 ``force_rmtree`` 语义忽略, 随后 ``copytree`` 就地补回被删的
    部分: 宁可留下几个多余文件, 也不让目标停在半删状态。

    Args:
        src: 内容来源目录。
        dst: 目标目录, 会被替换成 ``src`` 的内容。
    """
    force_rmtree(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def dir_fingerprint(path: Path) -> str:
    """
    对目录树做轻量指纹, 用于判断配置是否被改动过

    只取相对路径与文件大小, 不读内容: 只需区分「与某次已知状态是否一致」。

    Args:
        path: 目录路径, 不存在时返回空串指纹。

    Returns:
        十六进制摘要串。
    """

    if not path.is_dir():
        return ""

    digest = hashlib.sha256()
    for entry in sorted(path.rglob("*")):
        if not entry.is_file():
            continue
        try:
            stat_result = entry.stat()
        except OSError:
            continue
        digest.update(str(entry.relative_to(path)).encode("utf-8", "surrogatepass"))
        digest.update(str(stat_result.st_size).encode("ascii"))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class NativeConfigSnapshot:
    """
    一次脚本原生配置快照的归属与状态信息

    Attributes:
        script_id: 所属脚本, 防止跨脚本误恢复。
        original_exists: 快照时原生配置目录是否存在。
        baseline: 原始配置指纹, 用于识别「尚未被 MAS 改动」。
        injected: MAS 注入后的预期指纹, None 表示本次运行未注入。
    """

    script_id: str
    original_exists: bool
    baseline: str
    injected: str | None = None


def _snapshot_ready_path(snapshot_path: Path) -> Path:
    """快照提交标记路径, 用 .json 后缀复用配置读写原语。"""

    return snapshot_path.with_name(snapshot_path.name + ".ready.json")


def _snapshot_swap_paths(live_path: Path) -> tuple[Path, Path]:
    """换入过程的同卷临时目录(与原生配置目录同盘, 改名才可能成功)。"""

    return (
        live_path.with_name(live_path.name + ".automas-new"),
        live_path.with_name(live_path.name + ".automas-old"),
    )


def write_native_config_snapshot(
    snapshot_path: Path,
    *,
    script_id: str,
    original_exists: bool,
    baseline: str,
    injected: str | None = None,
) -> None:
    """
    原子写出快照归属信息, 标记该快照已完整提交

    Args:
        snapshot_path: 快照目录。
        script_id: 所属脚本, 供恢复时校验归属。
        original_exists: 快照时原生配置目录是否存在。
        baseline: 原始配置指纹。
        injected: MAS 注入后的预期指纹, 未注入传 None。
    """

    write_file(
        _snapshot_ready_path(snapshot_path),
        {
            "script_id": script_id,
            "original_exists": original_exists,
            "baseline": baseline,
            "injected": injected,
        },
    )


def read_native_config_snapshot(
    snapshot_path: Path, *, expected_script_id: str | None = None
) -> NativeConfigSnapshot | None:
    """
    读取已提交的快照归属信息

    Args:
        snapshot_path: 快照目录。
        expected_script_id: 期望归属的脚本, 不符视为无效。

    Returns:
        归属信息; 快照目录或标记不存在、内容无效、归属不符时返回 None。
    """

    ready_path = _snapshot_ready_path(snapshot_path)
    if not snapshot_path.is_dir() or not ready_path.exists():
        return None
    try:
        state = read_file(ready_path)
    except Exception:
        return None
    if not isinstance(state, dict):
        return None

    script_id = state.get("script_id")
    if not isinstance(script_id, str) or not script_id.strip():
        return None
    if expected_script_id is not None and script_id != expected_script_id:
        return None

    injected = state.get("injected")
    return NativeConfigSnapshot(
        script_id=script_id,
        original_exists=bool(state.get("original_exists", False)),
        baseline=str(state.get("baseline") or ""),
        injected=injected if isinstance(injected, str) else None,
    )


def clear_native_config_snapshot(snapshot_path: Path) -> None:
    """
    丢弃快照及其提交标记

    Args:
        snapshot_path: 快照目录。
    """

    force_rmtree(snapshot_path)
    with suppress(OSError):
        _snapshot_ready_path(snapshot_path).unlink()


def mark_native_config_injected(
    snapshot_path: Path,
    live_path: Path,
    *,
    script_id: str,
) -> None:
    """
    记录 MAS 注入后的原生配置指纹, 供崩溃恢复区分污染与用户改动

    MAS 把配置写进原生目录后调用; 未注入(直控)时不调用, 快照保持 injected
    为 None, 恢复时现场与基线一致即视为无污染。

    Args:
        snapshot_path: 快照目录。
        live_path: 被注入的脚本原生配置目录。
        script_id: 所属脚本, 与快照归属不符时静默跳过。
    """

    state = read_native_config_snapshot(snapshot_path, expected_script_id=script_id)
    if state is None:
        return
    write_native_config_snapshot(
        snapshot_path,
        script_id=state.script_id,
        original_exists=state.original_exists,
        baseline=state.baseline,
        injected=dir_fingerprint(live_path),
    )


def commit_native_config_snapshot(
    snapshot_path: Path,
    source_path: Path,
    *,
    script_id: str,
) -> bool:
    """
    备份脚本原生配置并提交为可恢复快照

    备份只写进快照目录, 全程不触碰原生配置; 拷贝中途崩溃会留下无标记的
    半成品快照, 下次恢复时按未提交丢弃。

    Args:
        snapshot_path: 快照目录(如 data/<script_id>/Temp)。
        source_path: 脚本原生配置目录。
        script_id: 所属脚本, 供恢复时校验归属。

    Returns:
        原生配置是否存在并已备份。
    """

    clear_native_config_snapshot(snapshot_path)
    if not source_path.exists():
        return False
    replace_dir(source_path, snapshot_path)
    write_native_config_snapshot(
        snapshot_path,
        script_id=script_id,
        original_exists=True,
        baseline=dir_fingerprint(snapshot_path),
    )
    return True


def swap_in_dir(src: Path, dst: Path) -> None:
    """
    用 src 整目录原子换入 dst: dst 要么保持原样, 要么完整变成 src

    与 replace_dir 的先清后拷不同, 这里先把 dst 同卷改名留底, 再把 src 的
    同卷副本改名就位, 全程不存在「dst 已被删除而新内容尚未就位」的中间态:
    脚本原生配置是要保的最后一份数据, 替换它的最后一步必须是改名而非删除。
    中断后现场只可能是「dst 缺失(留底还在)」「dst 完整」或「dst 原样」,
    前两种再调用一次本函数或恢复快照即可复原。

    src 与 dst 须同卷(与 dst 同级的临时副本天然满足); 留底与副本目录固定
    带 .automas-old / .automas-new 后缀, 每次调用开头都会清理上一次的残留。

    Args:
        src: 内容来源目录, 必须已存在。
        dst: 被替换的目标目录, 可以不存在。
    """

    if not src.is_dir():
        raise RuntimeError(f"配置换入的源目录不存在: {src}")

    staging_path, backup_path = _snapshot_swap_paths(dst)
    force_rmtree(staging_path)
    force_rmtree(backup_path)
    shutil.copytree(src, staging_path)
    dst_moved = False
    if dst.exists():
        dst.rename(backup_path)
        dst_moved = True
    try:
        staging_path.rename(dst)
    except BaseException:
        if dst_moved and not dst.exists():
            backup_path.rename(dst)
        raise
    finally:
        force_rmtree(staging_path)
        force_rmtree(backup_path)


def recover_native_config(
    snapshot_path: Path,
    live_path: Path,
    *,
    expected_script_id: str | None = None,
) -> str:
    """
    任务开始时处置上次运行残留的原生配置快照

    崩溃后的现场按序判定, 只有确属 MAS 中途退出才恢复:

    - 原生目录缺失或与注入后预期一致: 任务中途崩了且没人动过, 恢复回
      快照里的原始配置;
    - 原生目录与快照基线一致: 上次已恢复过或尚未注入, 幂等跳过;
    - 其它指纹: 用户在崩溃后手动改过原生配置, 只清理快照不覆盖, 避免把
      用户的新改动吃掉。

    Args:
        snapshot_path: 快照目录(与提交标记配套)。
        live_path: 脚本原生配置目录。
        expected_script_id: 期望归属的脚本, 不符则只清理不恢复。

    Returns:
        处置结果: restored / intact / skipped / cleared。
    """

    staging_path, backup_path = _snapshot_swap_paths(live_path)
    force_rmtree(staging_path)
    force_rmtree(backup_path)

    state = read_native_config_snapshot(
        snapshot_path, expected_script_id=expected_script_id
    )
    try:
        if state is None:
            return "cleared"

        if not live_path.exists():
            if state.original_exists:
                swap_in_dir(snapshot_path, live_path)
                return "restored"
            return "cleared"

        live = dir_fingerprint(live_path)
        if state.injected is not None and live == state.injected:
            if state.original_exists:
                swap_in_dir(snapshot_path, live_path)
            else:
                force_rmtree(live_path)
            return "restored"
        if live == state.baseline:
            return "intact"
        return "skipped"
    finally:
        clear_native_config_snapshot(snapshot_path)


def atomic_write(path: Path, data: bytes) -> None:
    """
    原子写, 写同目录固定名临时文件, fsync 后 replace 覆盖

    Args:
        path: 目标文件路径
        data: 待写入的字节内容
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with _WRITE_LOCK:
        try:
            tmp_path.write_bytes(data)
            # 数据落盘
            with tmp_path.open("rb+") as fh:
                fh.flush()
                os.fsync(fh.fileno())
            # 原子替换
            tmp_path.replace(path)
            # 目录项落盘, 仅在 Linux 下有效
            with suppress(OSError):
                with path.parent.open("rb") as dfh:
                    dfh.flush()
                    os.fsync(dfh.fileno())
        except BaseException:
            # 失败清理残留临时文件
            tmp_path.unlink(missing_ok=True)
            raise


def read_file(path: Path, *, format: str | None = None) -> dict[str, Any] | str:
    """
    按后缀读取配置文件, 传 ``format`` 可强制改用指定后缀的解析器

    Args:
        path: 文件路径, 未显式指定 ``format`` 时以其后缀决定解析格式
        format: 强制使用的解析器后缀 (含点), 忽略 ``path`` 实际后缀; 默认 ``None`` 按后缀推断

    Returns:
        dict[str, Any] | str: 已知格式解析后的结构; 未知格式返回原始字符串; 不存在返回空 ``{}``
    """
    if not path.exists():
        return {}
    _suffix = (format or path.suffix).lower()
    codec = _CODECS.get(_ALIASES.get(_suffix, _suffix))
    if codec is None:
        return decode_bytes(path.read_bytes())
    return codec[1](path.read_bytes())


def write_file(
    path: Path,
    payload: dict[str, Any] | str,
    *,
    encoding: str = "utf-8",
    format: str | None = None,
) -> None:
    """
    按后缀原子写入, 传 ``format`` 可强制改用指定后缀的序列化器

    - 已知格式: 序列化后写盘
    - 未知格式且传 ``str``: 不序列化, 直接写原字符串
    - 未知格式且传 ``dict`` 等非 str: 抛 ``ValueError``

    Args:
        path: 文件路径, 未显式指定 ``format`` 时以其后缀决定序列化格式
        payload: 已知格式为待写的 ``dict``; 未知格式须为 ``str``
        encoding: 写盘编码, 默认 ``utf-8``
        format: 强制使用的序列化器后缀 (含点), 忽略 ``path`` 实际后缀; 默认 ``None`` 按后缀推断
    """
    _suffix = (format or path.suffix).lower()
    codec = _CODECS.get(_ALIASES.get(_suffix, _suffix))
    if codec is not None:
        atomic_write(path, codec[0](payload, encoding))
        return
    if not isinstance(payload, str):
        raise ValueError(f"不支持的配置文件格式 `{_suffix}`，且内容非字符串")
    atomic_write(path, payload.encode(encoding))


def migrate_legacy_dir(old_path: Path, new_path: Path) -> bool:
    """
    首次访问时把整个旧目录搬迁到新路径, 用于落盘目录改名/搬家场景

    仅在新路径不存在且旧路径存在时执行, 天然只做一次: 一旦新路径落地
    (搬迁成功, 或调用方在此之后自行创建), 后续调用即判定新路径已存在而跳过。
    迁移失败 (如跨设备移动出错) 只记 warning, 不向上抛出, 不阻塞调用方
    继续在新路径上创建目录、写入文件。

    Args:
        old_path: 旧目录路径
        new_path: 新目录路径

    Returns:
        bool: 是否实际执行了搬迁
    """
    if new_path.exists() or not old_path.exists():
        return False
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
    except Exception as exc:  # noqa: BLE001 - 迁移失败不应阻塞调用方后续访问
        logger.warning(
            f"旧目录迁移失败，将继续使用新路径：{old_path} -> {new_path}：{exc}"
        )
        return False
    logger.info(f"旧目录已迁移：{old_path} -> {new_path}")
    return True
