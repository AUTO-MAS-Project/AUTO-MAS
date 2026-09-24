"""就地更新的事务应用与回滚。

**为什么不复制备份**：更新包解压后 400–570MB，复制一份做备份既占盘又把
「提交窗口」拉长到几百 MB 的 IO。改成把 stage 目录放在安装目录内（同卷），
备份和就位都用改名完成——改名只动元数据，提交窗口缩到几百次原子操作。

**为什么 journal 只写一次**：回滚规则完全由 backup 目录的现状决定，不需要
知道崩在第几个文件——

* ``replace`` 条目：``backup/<rel>`` 存在就把它移回去。崩在改名前（backup 无
  此项）、崩在两次改名之间（install 缺、backup 有）、崩在改名后（install 是
  新的、backup 有旧的），这一条规则三种情况都正确。
* ``create`` 条目：原本就没有该文件，``install/<rel>`` 存在就删掉；崩在创建前
  时删除是空操作。

所以计划写一次即可，逐文件刷盘反而会拖慢提交。

**从不删除包外的文件**：与 M7A、SRA 自己的更新器行为一致。用户放在
``tasks/currency_wars/strategies/`` 下的自定义策略因此得以保留（同名的上游
模板会被覆盖，这一点与上游一致）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

from .discover import HSRUpdateError
from .engines import get_spec

logger = get_logger("HSR 更新应用")

_WORK_DIRNAME = ".automas_update"
_JOURNAL_NAME = "journal.json"
_JOURNAL_SCHEMA = 1
_HASH_CHUNK = 256 * 1024

#: zip 展开上限，防炸弹包。M7A 全量包解压 565MB，留足余量。
_MAX_EXPANDED_BYTES = 8 * 1024**3
_MAX_ENTRIES = 100_000


@dataclass(frozen=True)
class ApplyResult:
    engine: str
    from_version: str | None
    to_version: str
    changed_files: int


class HSRUpdateApplyError(HSRUpdateError):
    """应用阶段失败。``rolled_back`` 为假表示目录可能处于中间状态。"""

    def __init__(self, message: str, *, rolled_back: bool) -> None:
        super().__init__(message)
        self.rolled_back = rolled_back


def work_dir(install_root: Path) -> Path:
    return install_root / _WORK_DIRNAME


def journal_path(install_root: Path) -> Path:
    return work_dir(install_root) / _JOURNAL_NAME


def apply_package(
    package: Path,
    install_root: Path,
    *,
    engine: str,
    from_version: str | None,
    to_version: str,
    seven_zip: Path | None,
) -> ApplyResult:
    """解包并就地更新。抛 :class:`HSRUpdateApplyError` 时已尽力回滚。"""

    work = work_dir(install_root)
    stage = work / "stage"
    backup = work / "backup"

    # 上一轮崩在中途时，backup 里存着唯一一份旧文件。下面的 _reset_dir 会把它
    # 清掉，所以**必须**先回滚——否则「崩溃后用户点一次手动更新」就会永久丢掉
    # 那些文件。调用方各自记得先回滚是靠不住的（API 入口就没有），把它做成这里
    # 的前置不变量。回滚没做成就拒绝继续：宁可不更新，也不能把旧文件冲掉。
    # rollback() 对损坏或不认识的 journal 是返回 False 而不是抛，所以返回值也要查。
    if has_pending_journal(install_root):
        logger.warning(f"HSR 更新：{install_root} 存在未完成的更新，先回滚再继续")
        if not rollback(install_root):
            raise HSRUpdateError(
                f"{install_root} 有无法识别的未完成更新记录，为保住备份已拒绝继续；"
                f"请检查 {journal_path(install_root)}"
            )

    try:
        _reset_dir(stage)
        _reset_dir(backup)
    except OSError as exc:
        _cleanup(work)
        raise HSRUpdateError(f"准备更新工作目录失败：{exc}") from exc

    try:
        _extract(package, stage, seven_zip=seven_zip)
        source_root = _strip_single_root(stage, get_spec(engine).executable)
        plan = _build_plan(source_root, install_root)
    except HSRUpdateError:
        _cleanup(work)
        raise
    except Exception as exc:  # noqa: BLE001 - 解包失败形态多，统一成可预期错误
        _cleanup(work)
        raise HSRUpdateError(f"解包失败：{exc}") from exc

    if not plan:
        _cleanup(work)
        return ApplyResult(engine, from_version, to_version, 0)

    journal = {
        "schema": _JOURNAL_SCHEMA,
        "engine": engine,
        "from_version": from_version,
        "to_version": to_version,
        "entries": [{"rel": rel, "action": action} for rel, action in plan],
    }
    try:
        _write_journal(install_root, journal)
    except OSError as exc:
        # 还没动安装目录，直接清掉 stage 走人，别把几百 MB 留在人家目录里。
        _cleanup(work)
        raise HSRUpdateError(f"写入更新记录失败：{exc}") from exc

    try:
        _commit(plan, source_root, install_root, backup)
    except Exception as exc:  # noqa: BLE001 - 任何失败都要尝试回滚
        logger.opt(exception=True).error(f"HSR 更新：应用 {engine} 更新失败，开始回滚")
        try:
            rollback(install_root)
        except Exception as rollback_exc:  # noqa: BLE001
            logger.opt(exception=True).error(f"HSR 更新：回滚同样失败：{rollback_exc}")
            raise HSRUpdateApplyError(
                f"更新失败且回滚未完成，{install_root} 可能处于中间状态："
                f"{exc}；回滚错误：{rollback_exc}",
                rolled_back=False,
            ) from exc
        raise HSRUpdateApplyError(
            f"更新失败，已回滚到原版本：{exc}", rolled_back=True
        ) from exc

    _cleanup(work)
    return ApplyResult(engine, from_version, to_version, len(plan))


def rollback(install_root: Path) -> bool:
    """按 journal 回滚。返回是否真的做了事（无 journal 时返回 ``False``）。"""

    journal_file = journal_path(install_root)
    try:
        journal = json.loads(journal_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if int(journal.get("schema", 0)) != _JOURNAL_SCHEMA:
        logger.warning(f"HSR 更新：无法识别的 journal 版本，跳过回滚：{journal_file}")
        return False

    work = work_dir(install_root)
    backup = work / "backup"
    failures: list[str] = []

    for entry in journal.get("entries") or []:
        rel = str(entry.get("rel") or "")
        if not rel:
            continue
        target = install_root / rel
        saved = backup / rel
        try:
            if saved.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(saved, target)
            elif entry.get("action") == "create" and target.exists():
                target.unlink()
        except OSError as exc:
            failures.append(f"{rel}: {exc}")

    if failures:
        preview = "；".join(failures[:5])
        raise HSRUpdateError(f"回滚未能完成（{len(failures)} 项失败）：{preview}")

    logger.info(f"HSR 更新：已回滚 {install_root} 的未完成更新")
    _cleanup(work)
    return True


def has_pending_journal(install_root: Path) -> bool:
    return journal_path(install_root).is_file()


# ── 内部实现 ──────────────────────────────────────────────────────────


def _commit(
    plan: list[tuple[str, str]],
    source_root: Path,
    install_root: Path,
    backup: Path,
) -> None:
    for rel, action in plan:
        target = install_root / rel
        staged = source_root / rel
        if action == "replace":
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, saved)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, target)


def _build_plan(source_root: Path, install_root: Path) -> list[tuple[str, str]]:
    """比出需要写入的文件。只看包内文件，包外的一律不动。"""

    plan: list[tuple[str, str]] = []
    for staged in source_root.rglob("*"):
        if not staged.is_file():
            continue
        rel = staged.relative_to(source_root).as_posix()
        target = install_root / rel
        if not target.exists():
            plan.append((rel, "create"))
        elif _differs(staged, target):
            plan.append((rel, "replace"))
    return plan


def _differs(staged: Path, target: Path) -> bool:
    try:
        staged_size = staged.stat().st_size
        target_size = target.stat().st_size
    except OSError:
        return True
    if staged_size != target_size:
        return True
    return _sha256(staged) != _sha256(target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(package: Path, stage: Path, *, seven_zip: Path | None) -> None:
    if package.suffix.casefold() == ".7z":
        if seven_zip is None:
            raise HSRUpdateError("需要 7z 解包器但未找到，请改用完整包更新")
        _extract_7z(package, stage, seven_zip)
        return
    _extract_zip(package, stage)


def _extract_7z(package: Path, stage: Path, seven_zip: Path) -> None:
    # 解包前先列一遍：和 zip 路径同一套上限，外加拒绝符号链接。7za 只读头部，
    # 170MB 的包实测 0.03 秒。
    _inspect_7z(package, seven_zip)
    completed = subprocess.run(
        [str(seven_zip), "x", "-aoa", f"-o{stage}", str(package)],
        capture_output=True,
        text=True,
        timeout=1800,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        tail = (completed.stdout or completed.stderr or "").strip()[-500:]
        raise HSRUpdateError(f"7z 解包失败（退出码 {completed.returncode}）：{tail}")
    _reject_symlinks(stage)


def _inspect_7z(package: Path, seven_zip: Path) -> None:
    """按 ``7za l -slt`` 的技术列表做解包前检查。

    正式版后端是提权跑的，7za 遇到符号链接条目**会真的建出链接**（未提权时
    只会报"privilege not held"），随后被 ``os.replace`` 搬进安装目录——所以
    符号链接必须在解包前就拒掉，不能指望之后再清。
    """

    completed = subprocess.run(
        [str(seven_zip), "l", "-slt", "-sccUTF-8", str(package)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        tail = (completed.stdout or completed.stderr or "").strip()[-500:]
        raise HSRUpdateError(f"7z 包无法读取（退出码 {completed.returncode}）：{tail}")

    # 输出格式：档案头 → "----------" → 每个条目一块，块间空行，块内 "键 = 值"。
    _, _, listing = completed.stdout.partition("----------")
    entries = 0
    total = 0
    for block in listing.split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(" = ")
            if sep:
                fields[key.strip()] = value.strip()
        name = fields.get("Path")
        if not name:
            continue
        entries += 1
        if entries > _MAX_ENTRIES:
            raise HSRUpdateError(f"更新包条目过多（超过 {_MAX_ENTRIES}），拒绝解包")
        total += int(fields.get("Size") or 0)
        if total > _MAX_EXPANDED_BYTES:
            raise HSRUpdateError(f"更新包展开体积异常（超过 {total} 字节），拒绝解包")
        if fields.get("Symbolic Link"):
            raise HSRUpdateError(f"更新包中存在符号链接，拒绝解包：{name}")
        if _escapes_stage(name):
            raise HSRUpdateError(f"更新包中存在越界路径：{name}")


def _escapes_stage(name: str) -> bool:
    """包内路径是否可能逃出 stage：绝对路径、盘符、或任一段是 ``..``。"""

    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        return True
    return ".." in normalized.split("/")


def _reject_symlinks(stage: Path) -> None:
    """解包后的兜底：stage 里不允许有任何符号链接，不管是谁解出来的。"""

    for path in stage.rglob("*"):
        if path.is_symlink():
            raise HSRUpdateError(
                f"解包结果中存在符号链接，拒绝继续：{path.relative_to(stage)}"
            )


def _extract_zip(package: Path, stage: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ENTRIES:
            raise HSRUpdateError(f"更新包条目过多（{len(infos)}），拒绝解包")
        total = sum(item.file_size for item in infos)
        if total > _MAX_EXPANDED_BYTES:
            raise HSRUpdateError(f"更新包展开体积异常（{total} 字节），拒绝解包")
        anchor = stage.resolve()
        for item in infos:
            destination = (stage / item.filename).resolve()
            # zip-slip：包内路径不得逃出 stage 目录。
            if destination != anchor and anchor not in destination.parents:
                raise HSRUpdateError(f"更新包中存在越界路径：{item.filename}")
        archive.extractall(stage)
    _reject_symlinks(stage)


def _strip_single_root(stage: Path, executable: str) -> Path:
    """脱掉单根文件夹。

    M7A 的 ``update.7z`` 是单根 ``update/``、``full.zip`` 是
    ``March7thAssistant_full/``；SRA 是扁平布局，没有根可脱。动态判断而不写死
    名字，上游改名也不会坏。

    单看「顶层只有一个目录」不足以判定：扁平包若恰好只含一个目录就会被误脱。
    用可执行文件当锚点消歧——它在顶层就说明这是扁平包。
    """

    if (stage / executable).exists():
        return stage
    entries = list(stage.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return stage


def _write_journal(install_root: Path, journal: dict[str, Any]) -> None:
    path = journal_path(install_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def _reset_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)


def _cleanup(work: Path) -> None:
    shutil.rmtree(work, ignore_errors=True)


__all__ = [
    "ApplyResult",
    "HSRUpdateApplyError",
    "apply_package",
    "has_pending_journal",
    "journal_path",
    "rollback",
    "work_dir",
]
