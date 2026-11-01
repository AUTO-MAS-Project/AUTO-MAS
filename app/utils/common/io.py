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
from time import monotonic, sleep
from typing import Any

import json5
import tomli_w
import yaml
from yaml import CSafeDumper, CSafeLoader

from app.utils.common.log.logger import get_logger

from .tools import decode_bytes

# 原生配置快照指纹算法版本。指纹口径变更时递增: 旧版本写下的快照无法与当前
# 目录比较, 恢复流程只保留现场, 不按指纹判定归属。
NATIVE_CONFIG_FINGERPRINT_VERSION = 2

logger = get_logger("路径迁移")


class ConfigCorruptedError(ValueError):
    """配置文件内容损坏到无法安全读取（解析失败 / 根节点非映射）。

    结构完整性（必备键、列表非空等）由调用方在返回的映射上自行校验,
    判为损坏时抛出本异常。继承 ``ValueError``: API 层未特别识别时按
    400 + 可读 message 返回; 恢复入口识别后转为「需用户确认」的 409。
    ``path`` 供报错文案给出损坏位置。读上游私有文件做枚举/守卫时的约定见
    ``.agents/skills/mas-script-specialized-adapter/references/blackbox-boundary.md``。
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(f"配置文件已损坏，无法安全读取：{self.path}")


# YAML 解析器拒绝的控制字符(除 \t \n \r): 映射为 None 即 translate 时丢弃
# \t \n \r 是 YAML 结构换行/缩进, 删除会把健康的多行文档压成一行导致解析失败
_INVALID_YAML_CHARS = dict.fromkeys(
    c for c in [*range(0x20), 0x7F] if c not in (0x09, 0x0A, 0x0D)
)

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
        lambda data: json.loads(decode_bytes(data).removeprefix("\ufeff")),
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
        lambda d, encoding: yaml.dump(
            d, Dumper=CSafeDumper, allow_unicode=True, sort_keys=False
        ).encode(encoding),
        lambda data: yaml.load(decode_bytes(data), Loader=CSafeLoader),
    ),
    ".sanitized.yaml": (
        lambda d, encoding: yaml.dump(
            d, Dumper=CSafeDumper, allow_unicode=True, sort_keys=False
        ).encode(encoding),
        # 容错读: 非原子写落盘的文件可能留下 NUL 填充, YAML 解析器遇到直接抛
        # ReaderError; 只取已知字段的调用方不应因此整个失败
        lambda data: yaml.load(
            decode_bytes(data).translate(_INVALID_YAML_CHARS), Loader=CSafeLoader
        ),
    ),
}

# 后缀别名, 共享同一序列化器: 别名后缀 -> 规范化后缀
# 查找时先归一化再查 _CODECS
_ALIASES: dict[str, str] = {
    ".jsonc": ".json5",
    ".yml": ".yaml",
}

# 进程内串行锁, 配置快照读取与原子写入共用，压缩快照时不占锁。
_WRITE_LOCK = threading.Lock()

# 同步保存持有配置执行入口，额外等待最多 170ms，不能按秒阻塞事件循环。
_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1)

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
            if path.is_symlink():
                path.unlink()
            elif path.is_junction():
                path.rmdir()
            elif not path.exists():
                return
            else:
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
    对目录树做内容指纹, 用于判断配置是否被改动过

    记录相对路径与文件内容, 避免同长度的用户改动被误判为原内容。

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
        digest.update(str(entry.relative_to(path)).encode("utf-8", "surrogatepass"))
        try:
            with entry.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    digest.update(chunk)
        except OSError:
            # 读取失败时让恢复流程保留快照, 不把未知现场当成安全状态。
            raise
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
        fingerprint_version: 写快照时的指纹算法版本, 与当前版本不符即不可比较。
    """

    script_id: str
    original_exists: bool
    baseline: str
    injected: str | None = None
    fingerprint_version: int = 0


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
            "fingerprint_version": NATIVE_CONFIG_FINGERPRINT_VERSION,
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
    fingerprint_version = state.get("fingerprint_version")
    return NativeConfigSnapshot(
        script_id=script_id,
        original_exists=bool(state.get("original_exists", False)),
        baseline=str(state.get("baseline") or ""),
        injected=injected if isinstance(injected, str) else None,
        fingerprint_version=(
            fingerprint_version if isinstance(fingerprint_version, int) else 0
        ),
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

    MAS 把配置写进原生目录后调用; 未注入(原生来源)时不调用, 快照保持 injected
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
    if dst.exists() or dst.is_symlink() or dst.is_junction():
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


def _preserve_legacy_snapshot(snapshot_path: Path) -> Path:
    """
    把指纹版本不符的旧快照改名留存

    旧快照里的原始配置仍是用户的数据, 但它的指纹由旧算法生成, 无法与当前目录
    比较。改名留存后, 下一次提交快照不会把它覆盖掉。

    Args:
        snapshot_path: 快照目录。

    Returns:
        改名后的快照目录。
    """

    index = 0
    while True:
        suffix = "" if index == 0 else f".{index}"
        target = snapshot_path.with_name(f"{snapshot_path.name}.legacy{suffix}")
        if not target.exists() and not _snapshot_ready_path(target).exists():
            break
        index += 1
    snapshot_path.rename(target)
    with suppress(OSError):
        _snapshot_ready_path(snapshot_path).rename(_snapshot_ready_path(target))
    return target


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

    快照由旧版本的指纹算法写下时无法比较, 一律改名留存并返回 legacy。

    Args:
        snapshot_path: 快照目录(与提交标记配套)。
        live_path: 脚本原生配置目录。
        expected_script_id: 期望归属的脚本, 不符则只清理不恢复。

    Returns:
        处置结果: restored / intact / skipped / cleared / legacy。
    """

    staging_path, backup_path = _snapshot_swap_paths(live_path)
    force_rmtree(staging_path)
    force_rmtree(backup_path)

    state = read_native_config_snapshot(
        snapshot_path, expected_script_id=expected_script_id
    )
    if state is None:
        result = "cleared"
    elif state.fingerprint_version != NATIVE_CONFIG_FINGERPRINT_VERSION:
        _preserve_legacy_snapshot(snapshot_path)
        return "legacy"
    elif not live_path.exists():
        if state.original_exists:
            swap_in_dir(snapshot_path, live_path)
            result = "restored"
        else:
            result = "cleared"
    else:
        live = dir_fingerprint(live_path)
        if state.injected is not None and live == state.injected:
            if state.original_exists:
                swap_in_dir(snapshot_path, live_path)
            else:
                force_rmtree(live_path)
            result = "restored"
        elif live == state.baseline:
            result = "intact"
        else:
            result = "skipped"

    clear_native_config_snapshot(snapshot_path)
    return result


def copy_file_snapshot(source: Path, destination: Path) -> bool:
    """与原子写互斥地复制文件；等待锁期间已消失的文件返回 False。"""
    with _WRITE_LOCK:
        # 枚举时看到的原子写临时文件可能已转正，不按后缀误删持久文件。
        if not source.exists():
            return False
        shutil.copy2(source, destination)
        return True


def _describe_path(path: Path) -> str:
    """尽力读取文件属性用于诊断，不打开内容或改变权限。"""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return "exists=False"
    except OSError as error:
        return (
            f"stat_errno={error.errno},stat_winerror={getattr(error, 'winerror', None)}"
        )
    attributes = getattr(info, "st_file_attributes", None)
    readonly = (
        bool(attributes & stat.FILE_ATTRIBUTE_READONLY)
        if attributes is not None
        else None
    )
    return (
        f"exists=True,is_dir={stat.S_ISDIR(info.st_mode)},"
        f"is_link={stat.S_ISLNK(info.st_mode)},"
        f"mode={stat.S_IMODE(info.st_mode):04o},"
        f"attributes={attributes},readonly={readonly}"
    )


def _replace_file(source: Path, target: Path) -> None:
    """仅对 Windows 拒绝访问和共享占用短重试，失败保留原异常。"""
    started = monotonic()
    for attempt in range(len(_REPLACE_RETRY_DELAYS) + 1):
        try:
            source.replace(target)
        except OSError as error:
            if getattr(error, "winerror", None) in (5, 32, 33) and attempt < len(
                _REPLACE_RETRY_DELAYS
            ):
                sleep(_REPLACE_RETRY_DELAYS[attempt])
                continue
            diagnostic = (
                f"原子替换失败: file={target.name}, attempts={attempt + 1}, "
                f"elapsed_ms={int((monotonic() - started) * 1000)}, "
                f"errno={error.errno},winerror={getattr(error, 'winerror', None)}, "
                f"source=[{_describe_path(source)}], "
                f"target=[{_describe_path(target)}], "
                f"parent=[{_describe_path(target.parent)}]"
            )
            error.add_note(diagnostic)
            # 原调用方负责异常上报，诊断用 INFO 避免额外生成一条 Sentry Issue。
            logger.info(diagnostic)
            raise
        if attempt:
            logger.info(
                f"文件替换重试后成功: file={target.name}, attempts={attempt + 1}, "
                f"elapsed_ms={int((monotonic() - started) * 1000)}"
            )
        return


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
            _replace_file(tmp_path, path)
            # 目录项落盘, 仅在 Linux 下有效
            with suppress(OSError):
                with path.parent.open("rb") as dfh:
                    dfh.flush()
                    os.fsync(dfh.fileno())
        except BaseException as error:
            # 清理失败不能覆盖最初的保存错误，保留两处信息供后续定位。
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                diagnostic = (
                    f"临时文件清理失败: operation=cleanup, file={tmp_path.name}, "
                    f"errno={cleanup_error.errno},"
                    f"winerror={getattr(cleanup_error, 'winerror', None)}"
                )
                error.add_note(diagnostic)
                logger.info(diagnostic)
            raise


def read_file(
    path: Path, *, format: str | None = None, raw: bytes | None = None
) -> dict[str, Any] | str:
    """
    按后缀读取配置文件, 传 ``format`` 可强制改用指定后缀的解析器

    Args:
        path: 文件路径, 未显式指定 ``format`` 时以其后缀决定解析格式
        format: 强制使用的解析器后缀 (含点), 忽略 ``path`` 实际后缀; 默认 ``None`` 按后缀推断
        raw: 预读的文件字节内容; 传入时不再重复读盘, 供 :func:`read_dict_file`
            复用首次读取结果, 避免同一文件读两次

    Returns:
        dict[str, Any] | str: 已知格式解析后的结构; 未知格式返回原始字符串; 不存在返回空 ``{}``
    """
    if not path.exists():
        return {}
    _suffix = (format or path.suffix).lower()
    codec = _CODECS.get(_ALIASES.get(_suffix, _suffix))
    content = path.read_bytes() if raw is None else raw
    if codec is None:
        return decode_bytes(content)
    return codec[1](content)


def _is_empty_yaml_document(
    path: Path, *, format: str | None = None, raw: bytes | None = None
) -> bool:
    """区分真正的空 YAML 文档与显式 ``null``。

    YAML 解析器对这两种内容都返回 ``None``，但配置文件只应把空白、
    注释和文档标记视为空文档；显式 ``null`` 仍然是错误的根节点。
    """

    suffix = (format or path.suffix).lower()
    normalized = _ALIASES.get(suffix, suffix)
    if normalized not in (".yaml", ".sanitized.yaml"):
        return False
    content = decode_bytes(path.read_bytes() if raw is None else raw)
    if normalized == ".sanitized.yaml":
        content = content.translate(_INVALID_YAML_CHARS)
    try:
        events = list(yaml.parse(content, Loader=CSafeLoader))
    except Exception:  # noqa: BLE001 - 读取入口已经给出统一损坏错误
        return False

    scalar_events = [
        event for event in events if isinstance(event, yaml.events.ScalarEvent)
    ]
    if not scalar_events:
        # 空白和注释没有文档节点；前一次解析已确认内容为空。
        return True
    if len(scalar_events) != 1:
        return False

    # PyYAML 把「---」表示为隐式空标量；显式 null、标签及锚点也可能
    # 使用同一节点值，需按解析事件区分，避免把坏配置当空文件覆盖。
    event = scalar_events[0]
    return event.value == "" and event.tag is None and event.anchor is None


def read_dict_file(
    path: Path, *, format: str | None = None, allow_empty: bool = False
) -> dict[str, Any]:
    """
    严格读取映射型配置文件: 解析失败或根节点非映射时抛 ``ConfigCorruptedError``

    ``allow_empty=True`` 时，空白、注释和文档标记组成的空 YAML 文档返回
    ``{}``；显式 ``null``、列表和标量仍按损坏处理。默认值保持严格语义，
    供需要区分「没有配置」与「配置损坏」的调用方使用。

    与 :func:`read_file` 的区别: 坏档显式失败而非静默返回原始值, 供备份
    拦截、恢复二次确认等需要区分「读不到」与「没有」的调用方使用, 杜绝
    ``read_file(x).get(...)`` 对未知后缀退回原始字符串再炸
    ``AttributeError`` 的事故形态 (#877 根因)。

    Args:
        path: 文件路径, 未显式指定 ``format`` 时以其后缀决定解析格式
        format: 强制使用的解析器后缀 (含点); 读上游非原子写落盘的 YAML
            (进程被杀/断电可能残留 NUL 填充) 建议传 ``.sanitized.yaml``
        allow_empty: 是否把真正的空 YAML 文档视为 ``{}``；显式 ``null``
            不受此选项放宽

    Returns:
        dict[str, Any]: 解析后的映射; 文件不存在返回空 ``{}``

    Raises:
        ConfigCorruptedError: 文件存在但解析失败或根节点非映射

    文件锁 / 竞态删除等读取失败（``OSError``）不是内容损坏, 原样上抛交调用
    方按读取失败处理, 不进入 409/强制恢复决策分支误导用户对好文件确认。
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
        data = read_file(path, format=format, raw=raw)
    except OSError:
        raise
    except Exception as exc:  # noqa: BLE001 - 解析层任何失败都按损坏上报
        raise ConfigCorruptedError(path) from exc
    if isinstance(data, dict):
        return data
    if (
        data is None
        and allow_empty
        and _is_empty_yaml_document(path, format=format, raw=raw)
    ):
        return {}
    raise ConfigCorruptedError(path)


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


def restore_injected_dict_values(current: dict, original: dict, injected: dict) -> None:
    """撤销仍等于注入值的字段，保留外部修改；原地更新 current。"""
    from copy import deepcopy

    missing = object()
    for key in original.keys() | injected.keys():
        before = original.get(key, missing)
        after = injected.get(key, missing)
        if before == after:
            continue
        actual = current.get(key, missing)
        if (
            isinstance(actual, dict)
            and isinstance(after, dict)
            and (before is missing or isinstance(before, dict))
        ):
            restore_injected_dict_values(
                actual, {} if before is missing else before, after
            )
            if before is missing and not actual:
                current.pop(key, None)
        elif actual == after:
            if before is missing:
                current.pop(key, None)
            else:
                current[key] = deepcopy(before)


def restore_config_injection_journal(
    journal: Path, path: Path, *, identity: dict
) -> str:
    """恢复带归属的配置注入日志；异安装日志归档，不覆盖新安装。"""
    from copy import deepcopy

    if not journal.exists():
        return "absent"
    state = read_dict_file(journal)
    if state.get("script_id") != identity["script_id"]:
        raise ValueError("配置恢复日志脚本身份不匹配")
    if state.get("root") != identity["root"]:
        index = 0
        while True:
            suffix = "" if index == 0 else f".{index}"
            archive = journal.with_name(f"{journal.name}.other-install{suffix}")
            if not archive.exists():
                journal.rename(archive)
                return "archived"
            index += 1
    if not isinstance(state.get("original"), dict) or not isinstance(
        state.get("injected"), dict
    ):
        raise ValueError("配置恢复日志内容无效")
    current = read_dict_file(path)
    restored = deepcopy(current)
    restore_injected_dict_values(restored, state["original"], state["injected"])
    if restored != current:
        write_file(path, restored)
    journal.unlink()
    return "restored"
