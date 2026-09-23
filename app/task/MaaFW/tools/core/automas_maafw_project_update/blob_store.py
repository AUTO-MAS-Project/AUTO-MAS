"""内嵌副本之间按内容共用大文件：同样的字节只在磁盘上存一份。

满足共用谓词（``projection.is_shared_path``：≥ 64 KB 且不在排除表）的文件按 sha256
存进 ``data/maafw_blobs/<ab>/<sha256>``，载荷与视图里的路径是指向它的 NTFS 硬链接。
运行时看到的就是普通文件——agent、runner、更新器都不用知道这回事；两个项目自带的
numpy、onnxruntime、MaaAgentBinary 只要字节相同就只占一份。

三条约束，都在 :meth:`RuntimeBlobStore.place` 里兑现：

- **永远不往已有文件里写。** 硬链接没有写时复制，往一个链接里写就是改所有项目的
  那份。落地新内容一律先 unlink 再链接 / 复制；内容没变的文件连碰都不碰。
- **小文件不进库。** 锁文件、``.pth``、dist-info 元数据这类几十字节的东西是最可能被
  原地改写的（M9A 的 bootstrap 就往 ``python/*.lock`` 里追加写），而省空间的大头是
  几十 MB 的原生库；只对 ``LINK_MIN_BYTES`` 以上的文件做共用。
- **链接失败就复制。** 跨卷、非 NTFS、链接数到上限（NTFS 一个文件最多 1023 个链接）
  都退回普通复制，导入与更新绝不因为库的问题失败。

代价与边界：库文件不设只读（否则 pip 删不掉旧包、``os.replace`` 类热更新也会被打断）。
Windows 11 本机实测：一个 inode 正被别的进程映射（DLL 已加载）时，**只有被映射的那个
目录项**不能删除 / 被 ``os.replace`` 覆盖 / 以写方式打开；同一 inode 的其它硬链接名照样
可以删、重链、rename、被替换，含被映射文件的目录也能 rename。所以「A 在跑、B 换掉
自己那份同内容的链接」不会被挡住。仍保留兜底：先 rename 再删、删不掉留给启动期清理
（旧系统版本、杀软持句柄这类情况实验覆盖不到）。回收在启动期做：``st_nlink == 1`` 的
blob 没有任何副本 / 载荷引用，删掉。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

BLOB_STORE_DIR_NAME = "maafw_blobs"
LINK_MIN_BYTES = 64 * 1024
_TEMP_SUFFIX = ".tmp-"
_COPY_CHUNK = 1024 * 1024

try:  # Windows only
    import _winapi  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - POSIX
    _winapi = None


@dataclass
class PlaceResult:
    action: str  # "linked" | "copied" | "unchanged" | "skipped"
    size: int
    # 算过内容哈希时顺带带回（``ingest_in_place`` 总会算；``place`` 不填）。
    digest: str = ""


@dataclass
class GarbageReport:
    removed_blobs: int = 0
    removed_bytes: int = 0
    removed_temps: int = 0


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RuntimeBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @classmethod
    def default(cls, base: Path | None = None) -> RuntimeBlobStore:
        return cls(
            (base if base is not None else Path.cwd()) / "data" / BLOB_STORE_DIR_NAME
        )

    def blob_path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def eligible(self, size: int) -> bool:
        return size >= LINK_MIN_BYTES

    def place(self, source: Path, destination: Path) -> PlaceResult:
        """把 ``source`` 的内容放到 ``destination``。

        库里有同内容就硬链接过去，没有就先入库再链接；``destination`` 已经是同样的
        内容就什么都不做（也就不会去碰可能正被别的项目映射着的旧文件）。
        """

        size = source.stat().st_size
        if not self.eligible(size):
            _copy_fresh(source, destination)
            return PlaceResult("copied", size)

        digest = sha256_file(source)
        if destination.is_file() and not destination.is_symlink():
            try:
                if (
                    destination.stat().st_size == size
                    and sha256_file(destination) == digest
                ):
                    return PlaceResult("unchanged", size)
            except OSError:
                pass

        blob = self.blob_path(digest)
        if not self._ensure_blob(source, blob, digest):
            _copy_fresh(source, destination)
            return PlaceResult("copied", size)

        destination.parent.mkdir(parents=True, exist_ok=True)
        _unlink(destination)
        try:
            os.link(blob, destination)
        except OSError:
            _copy_fresh(source, destination)
            return PlaceResult("copied", size)
        return PlaceResult("linked", size)

    def ingest_in_place(self, path: Path) -> PlaceResult:
        """把一个已经在位的私有文件就地收进库，自己换成指向库的硬链接。

        内容一个字节都不写：库里没有同内容 → 给这个文件再挂一个库里的名字（同一
        inode，``st_nlink`` 1 → 2）；库里已有（复核过内容）→ 在旁边从库链出一个临时名，
        再 ``os.replace`` 换掉原来的目录项。< 64 KB 不入库（``skipped``）；本来就是库里
        那个 inode 时 ``unchanged``；任何一步失败都保持原文件不动（``copied``，即仍私有）。
        """

        info = path.stat()
        size = info.st_size
        if not self.eligible(size):
            return PlaceResult("skipped", size)
        digest = sha256_file(path)
        blob = self.blob_path(digest)
        try:
            if blob.is_file():
                blob_info = blob.stat()
                if (blob_info.st_ino, blob_info.st_dev) == (info.st_ino, info.st_dev):
                    return PlaceResult("unchanged", size, digest)
                if sha256_file(blob) != digest:
                    # 库里这份被写穿过：挪开隔离，已经链着它的副本不受影响；这个文件接替入库。
                    blob.rename(
                        blob.with_name(f"{blob.name}.corrupt-{uuid.uuid4().hex[:8]}")
                    )
            blob.parent.mkdir(parents=True, exist_ok=True)
            if not blob.is_file():
                temporary = blob.with_name(
                    f"{blob.name}{_TEMP_SUFFIX}{uuid.uuid4().hex[:8]}"
                )
                os.link(path, temporary)
                try:
                    os.replace(temporary, blob)
                finally:
                    _unlink_quiet(temporary)
                return PlaceResult("linked", size, digest)
            temporary = path.with_name(
                f".{path.name}{_TEMP_SUFFIX}{uuid.uuid4().hex[:8]}"
            )
            os.link(blob, temporary)
            try:
                os.replace(temporary, path)
            finally:
                _unlink_quiet(temporary)
            return PlaceResult("linked", size, digest)
        except OSError:
            return PlaceResult("copied", size, digest)

    def _ensure_blob(self, source: Path, blob: Path, digest: str) -> bool:
        """库里有就复核一遍（被原地改过的 blob 不能再让新项目沾上），没有就入库。"""

        try:
            if blob.is_file():
                if sha256_file(blob) == digest:
                    return True
                # 有人往共用文件里写过：把坏的挪开（已经链着它的副本不受影响），重新入库。
                blob.rename(
                    blob.with_name(f"{blob.name}.corrupt-{uuid.uuid4().hex[:8]}")
                )
            blob.parent.mkdir(parents=True, exist_ok=True)
            temporary = blob.with_name(
                f"{blob.name}{_TEMP_SUFFIX}{uuid.uuid4().hex[:8]}"
            )
            shutil.copy2(source, temporary)
            os.replace(temporary, blob)
            return True
        except OSError:
            return False

    def collect_garbage(self) -> GarbageReport:
        """删掉没有任何副本引用的 blob（只剩库里这一个链接）、半成品与被隔离的坏文件。"""

        report = GarbageReport()
        if not self.root.is_dir():
            return report
        for shard in sorted(self.root.iterdir()):
            if not shard.is_dir():
                continue
            for entry in sorted(shard.iterdir()):
                try:
                    if not entry.is_file():
                        continue
                    stat = entry.stat()
                    if _TEMP_SUFFIX in entry.name or ".corrupt-" in entry.name:
                        entry.unlink()
                        report.removed_temps += 1
                        continue
                    if stat.st_nlink <= 1:
                        entry.unlink()
                        report.removed_blobs += 1
                        report.removed_bytes += stat.st_size
                except OSError:
                    continue
            try:
                shard.rmdir()  # 空了才删得掉，非空会抛
            except OSError:
                pass
        return report


def _unlink(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _copy_fresh(source: Path, destination: Path) -> None:
    """复制到一个新文件：先删旧的，不往已有文件（可能是共用链接）里写。"""

    destination.parent.mkdir(parents=True, exist_ok=True)
    _unlink(destination)
    shutil.copy2(source, destination)


# --------------------------------------------------------------------------
# 写穿防线：往 staging / 视图 / 载荷放文件的唯一方式
# --------------------------------------------------------------------------


_ERROR_FILE_EXISTS = (80, 183)  # ERROR_FILE_EXISTS / ERROR_ALREADY_EXISTS


def _copy_exclusive(source: Path, destination: Path) -> None:
    """复制成一个**新**文件（连同修改时间）：目标已存在就抛 ``FileExistsError``，绝不以
    ``wb`` 打开一个已有的（可能是载荷硬链接的）文件。Windows 上走 ``CopyFile2`` +
    ``COPY_FILE_FAIL_IF_EXISTS``（一次系统调用带属性与时间戳，比逐字节读写 + copystat
    快一倍多），不可用时退回 ``open("xb")``。"""

    if _winapi is not None and hasattr(_winapi, "CopyFile2"):
        flags = _winapi.COPY_FILE_FAIL_IF_EXISTS | getattr(
            _winapi, "COPY_FILE_ALLOW_DECRYPTED_DESTINATION", 0
        )
        try:
            _winapi.CopyFile2(str(source), str(destination), flags)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) in _ERROR_FILE_EXISTS:
                raise FileExistsError(str(destination)) from exc
            # 其它失败（只读源、权限……）：目标若已被它建出一半，那是我们自己刚建的，删掉重来。
            try:
                os.unlink(destination)
            except OSError:
                pass
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, _COPY_CHUNK)
    shutil.copystat(source, destination)


def place_fresh(
    source: Path, destination: Path, *, link: bool, make_parent: bool = True
) -> str:
    """把 ``source`` 放到 ``destination``：链接（``link=True``）或复制成新文件。

    返回 ``"linked"`` / ``"copied"``。两种方式都是**独占新建**——``os.link`` 与
    ``COPY_FILE_FAIL_IF_EXISTS`` / ``open("xb")`` 遇到已存在的目标只会失败，不会写进去；
    失败就先 ``unlink`` 目标再建一次。所以任何已存在的目标（可能是载荷 / blob 的硬链接）
    都只会被摘掉目录项，内容一个字节不动。复制只在链接失败时兜底。
    """

    if make_parent:
        destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            if link:
                try:
                    os.link(source, destination)
                    return "linked"
                except FileExistsError:
                    raise
                except OSError:
                    pass  # 跨卷、链接数到上限、非 NTFS：退回复制
            _copy_exclusive(source, destination)
            return "copied"
        except FileExistsError:
            if attempt:
                raise
            os.unlink(destination)
    raise AssertionError("unreachable")


__all__ = [
    "BLOB_STORE_DIR_NAME",
    "GarbageReport",
    "LINK_MIN_BYTES",
    "PlaceResult",
    "RuntimeBlobStore",
    "place_fresh",
    "sha256_file",
]
