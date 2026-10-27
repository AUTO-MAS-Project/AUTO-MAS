"""隔离 venv 跨视图共用：键、引用记录、跨进程锁。

隔离 venv 原来按项目（视图）路径哈希定位，同一项目建几个脚本就有几份一模一样的 venv，
每份首跑各装一遍依赖。现在目录名按**装进去的东西**算（方案「MFW副本复用与版本切换」§7-5）：

- **键** = 依赖清单（``requirements.txt`` 洗过、maafw 已钉成确切版本、补过引导包之后的那份，
  即 manifest 的 ``requirements``）+ maafw requirement + 宿主身份，sha256 取 16 位，目录名
  ``maafw_venv_<16hex>``（老的按路径哈希的是 12 位，长度不同、不会撞名）。任一不同就是另一个
  目录，不共用，也不会为了迁就某个视图去改别人那份。
- **宿主身份**：平台、CPU 架构、解释器实现。venv 根目录本来就在本机这份安装的
  ``config/maafw_agent_venvs`` 下，跨安装不会相遇；引导解释器具体是哪一个（便携 Python、
  宿主 / worker 自己、PATH 上的）不进目录名——宿主与 worker 挑出来的本来就可能不同，按它分
  会让 worker 在宿主刚建好的旁边再建一份。它记在 venv 自己的 ``pyvenv.cfg`` 里，引导解释器
  没了按「基解释器已不存在」重建（那时用它的视图本来就都起不来）。
- **视图引用**：准备成功后在 ``<根>/.refs/<视图路径哈希>.json`` 记下本视图这次用的目录。
  回收按「存活视图引用的目录」算，不再按路径推名字；建计划时同样先看它，项目没自带原生库、
  maafw 版本要等 runner 解析出来才定的那种，计划阶段才能拿到准备时实际用的那份。
- **跨进程锁**：宿主与 worker 是两个进程，两个视图可能同时准备同一份 venv（宿主为 A 准备、
  worker 为 B 运行前准备）。``<根>/.locks/<目录名>.lock`` 上的字节锁把准备串行化，等的一方看到的
  一定是建好的或没建的，不会把别人建了一半的当「不完整」删掉。锁文件不删（同
  ``project_update.state.DurableFileLock`` 的理由）。

本模块只用标准库：worker 的导入闭包会经 ``agent_env`` 拉到这里。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import platform
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

try:  # Windows 用字节区间锁，POSIX 用 lockf，与 DurableFileLock 一致
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

try:
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - Windows
    fcntl = None

logger = logging.getLogger("automas.maafw.agent_env.venv_share")

AGENT_VENV_DIR_PREFIX = "maafw_venv_"
DEFAULT_AGENT_VENV_ROOT_PARTS = ("config", "maafw_agent_venvs")
SHARED_VENV_KEY_SCHEMA = 2
SHARED_VENV_DIGEST_LENGTH = 16
LEGACY_VENV_DIGEST_LENGTH = 12
VENV_REFS_DIR_NAME = ".refs"
VENV_LOCKS_DIR_NAME = ".locks"
#: 重建时旧目录先改名成 ``<目录名>.trash-<随机>`` 再删：删不完的留给启动期回收（前缀相同）。
VENV_TRASH_MARKER = ".trash-"
VENV_REF_SCHEMA = 1
#: 等另一处准备同一份 venv 的上限。建 venv + 逐个镜像装依赖最坏要十几分钟。
VENV_LOCK_TIMEOUT_SECONDS = 30 * 60
VENV_LOCK_POLL_SECONDS = 0.2
VENV_LOCK_PROGRESS_SECONDS = 60.0


def default_agent_venv_root() -> Path:
    return Path.cwd().joinpath(*DEFAULT_AGENT_VENV_ROOT_PARTS)


def resolve_agent_venv_root(managed_env_root: str | Path | None) -> Path:
    root = (
        Path(managed_env_root)
        if managed_env_root is not None
        else default_agent_venv_root()
    )
    return root.resolve()


def _path_key(path: str | Path) -> str:
    key = str(Path(path).resolve())
    if os.name == "nt":
        key = key.lower()
    return key


def legacy_isolated_venv_name(project_path: str | Path) -> str:
    """老规则的目录名：按项目（视图）路径哈希。只用于认出升级前建的那份。"""

    digest = hashlib.sha1(_path_key(project_path).encode("utf-8")).hexdigest()
    return f"{AGENT_VENV_DIR_PREFIX}{digest[:LEGACY_VENV_DIGEST_LENGTH]}"


def agent_venv_host_identity() -> dict[str, str]:
    """键里的宿主身份（见模块说明：不含具体的引导解释器）。"""

    return {
        "platform": sys.platform,
        "machine": (platform.machine() or "unknown").lower(),
        "implementation": sys.implementation.name,
    }


def shared_venv_key_inputs(
    project_path: str | Path, *, runner_maafw_version: str | None = None
) -> dict[str, Any]:
    """算键用的输入。依赖清单读不了（``-r`` 越界等）时照原样抛 ``MaaFWAgentEnvError``。"""

    # 延迟导入：env 在模块级 import planner，planner 在模块级 import 本模块。
    from app.task.MaaFW.tools.core.runner.environment import (
        resolve_project_maafw_requirement,
    )

    from .env import _load_project_agent_requirements

    project = Path(project_path).resolve()
    return {
        "schema": SHARED_VENV_KEY_SCHEMA,
        "requirements": _load_project_agent_requirements(
            project, runner_maafw_version=runner_maafw_version
        ),
        "maafw": resolve_project_maafw_requirement(
            project, runner_maafw_version=runner_maafw_version
        ),
        "host": agent_venv_host_identity(),
    }


def shared_venv_name(inputs: dict[str, Any]) -> str:
    payload = json.dumps(
        inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{AGENT_VENV_DIR_PREFIX}{digest[:SHARED_VENV_DIGEST_LENGTH]}"


def is_shared_venv_name(name: str) -> bool:
    if not name.startswith(AGENT_VENV_DIR_PREFIX):
        return False
    digest = name[len(AGENT_VENV_DIR_PREFIX) :]
    return len(digest) == SHARED_VENV_DIGEST_LENGTH and all(
        char in "0123456789abcdef" for char in digest
    )


def _is_plain_venv_name(name: str) -> bool:
    """引用记录里只认这两种目录名，挡住 ``..`` 之类越出根目录的写法。"""

    if not name.startswith(AGENT_VENV_DIR_PREFIX):
        return False
    digest = name[len(AGENT_VENV_DIR_PREFIX) :]
    return len(digest) in {
        SHARED_VENV_DIGEST_LENGTH,
        LEGACY_VENV_DIGEST_LENGTH,
    } and all(char in "0123456789abcdef" for char in digest)


# ---------------------------------------------------------------- 视图引用记录


def venv_ref_path(root: str | Path, project_path: str | Path) -> Path:
    digest = hashlib.sha1(_path_key(project_path).encode("utf-8")).hexdigest()[:16]
    return Path(root) / VENV_REFS_DIR_NAME / f"{digest}.json"


class VenvRefError(RuntimeError):
    """引用记录在、却读不出来：调用方不能据此判断「没人用」。"""


def read_venv_ref(
    root: str | Path, project_path: str | Path, *, strict: bool = False
) -> dict[str, Any] | None:
    """读本视图的引用记录。没有返回 ``None``；读坏了按 ``strict`` 抛或当没有。"""

    path = venv_ref_path(root, project_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001 - 坏记录的处理交给调用方
        if strict:
            raise VenvRefError(f"隔离 venv 引用记录读不出来: {path} - {exc}") from exc
        return None
    if (
        not isinstance(payload, dict)
        or not _is_plain_venv_name(str(payload.get("venv") or ""))
        or _path_key(str(payload.get("projectPath") or "") or ".")
        != _path_key(project_path)
    ):
        if strict:
            raise VenvRefError(f"隔离 venv 引用记录内容不对: {path}")
        return None
    return payload


def write_venv_ref(
    root: str | Path,
    project_path: str | Path,
    *,
    venv_name: str,
    plan_name: str | None,
) -> None:
    path = venv_ref_path(root, project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": VENV_REF_SCHEMA,
        "projectPath": str(Path(project_path).resolve()),
        "venv": venv_name,
        # 建计划时（还不知道 runner 的 maafw 版本）算出的键：建计划时它对得上才信这条记录。
        "planKey": plan_name,
        "updatedAt": time.time(),
    }
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def remove_venv_ref(root: str | Path, project_path: str | Path) -> None:
    try:
        venv_ref_path(root, project_path).unlink(missing_ok=True)
    except OSError:
        pass


def iter_venv_refs(root: str | Path) -> Iterator[tuple[Path, dict[str, Any] | None]]:
    """``(记录文件, 内容)``；读不出来的内容是 ``None``。"""

    refs_dir = Path(root) / VENV_REFS_DIR_NAME
    try:
        entries = sorted(refs_dir.glob("*.json"))
    except OSError:
        return
    for entry in entries:
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = None
        yield entry, payload if isinstance(payload, dict) else None


# ---------------------------------------------------------------- 回收


def collect_orphan_agent_venvs(
    root: str | Path,
    live_project_paths: Iterable[str | Path],
    *,
    plan_name_for: Callable[[Path], str | None] | None = None,
) -> list[Path]:
    """列出已无存活视图引用的隔离 venv（含重建时改名留下的 ``*.trash-*``）。

    存活集合 = 每个存活视图引用记录里的目录 ∪ 它建计划时会算出的目录（``plan_name_for``，
    引用记录丢了也保得住）∪ 没有引用记录的视图按老规则算出的目录（升级后还没准备过的
    视图，第一跑要沿用它）。存活视图的引用记录在、却读不出来时整轮不回收（抛
    ``VenvRefError``）：不知道它在用哪一份，宁可不删。
    """

    root_path = Path(root).resolve()
    expected: set[str] = set()
    for raw in live_project_paths:
        project = Path(raw)
        ref = read_venv_ref(root_path, project, strict=True)
        if ref is not None:
            expected.add(str(ref["venv"]))
        else:
            expected.add(legacy_isolated_venv_name(project))
        if plan_name_for is not None:
            try:
                name = plan_name_for(project)
            except Exception:  # noqa: BLE001 - 算不出来就只靠引用记录
                name = None
            if name:
                expected.add(name)
    try:
        entries = sorted(root_path.iterdir())
    except OSError:
        return []
    return [
        entry
        for entry in entries
        if entry.is_dir()
        and entry.name.startswith(AGENT_VENV_DIR_PREFIX)
        and entry.name not in expected
    ]


def collect_stale_venv_refs(
    root: str | Path, live_project_paths: Iterable[str | Path]
) -> list[Path]:
    """不属于任何存活视图的引用记录（删掉的脚本、更新预检的 staging）。"""

    live = {_path_key(path) for path in live_project_paths}
    stale: list[Path] = []
    for entry, payload in iter_venv_refs(root):
        project = str((payload or {}).get("projectPath") or "")
        if payload is None or not project or _path_key(project) not in live:
            stale.append(entry)
    return stale


# ---------------------------------------------------------------- 锁

_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}
_HELD = threading.local()


def _lock_key(venv_path: Path) -> str:
    return os.path.normcase(str(venv_path.resolve())).casefold()


def venv_thread_lock(venv_path: Path) -> threading.RLock:
    key = _lock_key(venv_path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def venv_lock_file(venv_path: Path) -> Path:
    return venv_path.parent / VENV_LOCKS_DIR_NAME / f"{venv_path.name}.lock"


def _try_os_lock(handle: Any) -> bool:
    try:
        if os.name == "nt":
            if msvcrt is None:  # pragma: no cover - defensive
                return True
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        if fcntl is None:  # pragma: no cover - defensive
            return True
        fcntl.lockf(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0, os.SEEK_SET)
        return True
    except (BlockingIOError, PermissionError):
        return False
    except OSError as exc:
        # msvcrt 对被占用的区间报 EACCES / EDEADLK
        if getattr(exc, "errno", None) in {11, 13, 16, 35, 36}:
            return False
        raise


def _release_os_lock(handle: Any) -> None:
    try:
        if os.name == "nt":
            if msvcrt is not None:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        elif fcntl is not None:
            fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, 0, os.SEEK_SET)
    except OSError:
        pass


def _open_lock_handle(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
    except OSError:
        handle.close()
        raise
    return handle


class VenvLockTimeout(TimeoutError):
    pass


@contextlib.contextmanager
def isolated_venv_guard(
    venv_path: str | Path,
    *,
    log: Callable[[str], None] | None = None,
    timeout: float | None = VENV_LOCK_TIMEOUT_SECONDS,
    blocking: bool = True,
) -> Iterator[bool]:
    """本进程内按线程锁、跨进程按锁文件，串行化对同一份隔离 venv 的准备 / 删除。

    同一线程重入不再碰锁文件（Windows 上同一进程的第二个句柄也拿不到同一字节）。
    ``blocking=False`` 时拿不到就 yield ``False``、什么都不等（回收用）。
    """

    path = Path(venv_path).resolve()
    key = _lock_key(path)
    held: dict[str, int] = getattr(_HELD, "counts", None) or {}
    _HELD.counts = held
    thread_lock = venv_thread_lock(path)
    if not thread_lock.acquire(blocking=blocking):
        yield False
        return
    try:
        if held.get(key):
            held[key] += 1
            try:
                yield True
            finally:
                held[key] -= 1
            return
        handle = _open_lock_handle(venv_lock_file(path))
        try:
            started = time.monotonic()
            next_progress = VENV_LOCK_PROGRESS_SECONDS
            announced = False
            while not _try_os_lock(handle):
                if not blocking:
                    yield False
                    return
                elapsed = time.monotonic() - started
                if not announced and log is not None:
                    log(f"[Python环境] 隔离 venv 正由另一处准备，等它完成: {path}")
                    announced = True
                if timeout is not None and elapsed >= timeout:
                    raise VenvLockTimeout(
                        f"等另一处准备隔离 venv 超时（{elapsed:.0f} 秒）: {path}"
                    )
                if elapsed >= next_progress and log is not None:
                    log(
                        f"[Python环境] 仍在等另一处准备隔离 venv（已等 {elapsed:.0f} 秒）: {path}"
                    )
                    next_progress = elapsed + VENV_LOCK_PROGRESS_SECONDS
                time.sleep(VENV_LOCK_POLL_SECONDS)
            if announced and log is not None:
                log(
                    f"[Python环境] 另一处已准备完隔离 venv（等了 {time.monotonic() - started:.0f} 秒）: {path}"
                )
            held[key] = 1
            try:
                yield True
            finally:
                held.pop(key, None)
                _release_os_lock(handle)
        finally:
            handle.close()
    finally:
        thread_lock.release()


__all__ = [
    "AGENT_VENV_DIR_PREFIX",
    "VENV_TRASH_MARKER",
    "VenvLockTimeout",
    "VenvRefError",
    "agent_venv_host_identity",
    "collect_orphan_agent_venvs",
    "collect_stale_venv_refs",
    "default_agent_venv_root",
    "is_shared_venv_name",
    "isolated_venv_guard",
    "legacy_isolated_venv_name",
    "read_venv_ref",
    "remove_venv_ref",
    "resolve_agent_venv_root",
    "shared_venv_key_inputs",
    "shared_venv_name",
    "venv_lock_file",
    "venv_ref_path",
    "write_venv_ref",
]
