"""内嵌副本之间按内容共用运行时文件：同样的字节只在磁盘上存一份。

副本里 ``python/``、``maafw/``、``runtimes/<rid>/native`` 这些运行时目录的文件按 sha256
存进 ``data/maafw_blobs/<ab>/<sha256>``，副本里的路径是指向它的 NTFS 硬链接。运行时
看到的就是普通文件——agent、runner、更新器都不用知道这回事；两个项目自带的 numpy、
onnxruntime、MaaAgentBinary 只要字节相同就只占一份。

三条约束，都在 :meth:`RuntimeBlobStore.place` 里兑现：

- **永远不往已有文件里写。** 硬链接没有写时复制，往一个链接里写就是改所有项目的
  那份。落地新内容一律先 unlink 再链接 / 复制；内容没变的文件连碰都不碰。
- **小文件不进库。** 锁文件、``.pth``、dist-info 元数据这类几十字节的东西是最可能被
  原地改写的（M9A 的 bootstrap 就往 ``python/*.lock`` 里追加写），而省空间的大头是
  几十 MB 的原生库；只对 ``LINK_MIN_BYTES`` 以上的文件做共用。
- **链接失败就复制。** 跨卷、非 NTFS、链接数到上限（NTFS 一个文件最多 1023 个链接）
  都退回普通复制，导入与更新绝不因为库的问题失败。

代价与边界：库文件不设只读（否则 pip 删不掉旧包）；两个项目共用同一个 DLL 时，其中
一个正在运行（DLL 被映射）会挡住另一个项目替换它——只在「A 在跑、B 恰好要换同一份
旧库」时出现，落地事务照常回滚。回收在启动期做：``st_nlink == 1`` 的 blob 没有任何
副本引用，删掉。
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


@dataclass
class PlaceResult:
    action: str  # "linked" | "copied" | "unchanged"
    size: int


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


def _copy_fresh(source: Path, destination: Path) -> None:
    """复制到一个新文件：先删旧的，不往已有文件（可能是共用链接）里写。"""

    destination.parent.mkdir(parents=True, exist_ok=True)
    _unlink(destination)
    shutil.copy2(source, destination)


__all__ = [
    "BLOB_STORE_DIR_NAME",
    "GarbageReport",
    "LINK_MIN_BYTES",
    "PlaceResult",
    "RuntimeBlobStore",
    "sha256_file",
]
