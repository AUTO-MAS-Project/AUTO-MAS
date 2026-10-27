"""查出谁占着文件：换视图（目录 rename）被拒时，在告警里尽力点出占用者。

用 Windows Restart Manager（``rstrtmgr.dll``：RmStartSession / RmRegisterResources / RmGetList /
RmEndSession）按文件查打开它的进程。**一律 best effort**：非 Windows、调用失败、权限不够、超时，
都只是返回空，绝不抛异常——调用方的重试 / 降级行为不能因为查占用者而改变。

Restart Manager 只认文件，不认目录，也看不到「当前工作目录在里面」的进程：目录 rename 被拒时
在目录里挑一批最可能被占着的文件（可执行文件、动态库、扩展模块、日志）去查，查不到也不代表
没人占。只依赖标准库（psutil 有就用来取进程名），不碰宿主模块。
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

#: 目录里挑去查的文件后缀：运行中的进程最常一直开着的那几类。
_CANDIDATE_SUFFIXES = frozenset({".exe", ".dll", ".pyd", ".log", ".db", ".sqlite"})
#: 最多查多少个文件、最多走多少个目录项：视图可能有上万个文件，不能拖住告警。
_MAX_CANDIDATES = 512
_MAX_VISITED = 20000
#: 告警里最多列几个占用者。
_MAX_LISTED = 5
#: ERROR_ACCESS_DENIED / ERROR_SHARING_VIOLATION / ERROR_LOCK_VIOLATION
_LOCK_WINERRORS = frozenset({5, 32, 33})


def lock_candidates(path: Path) -> list[Path]:
    """要拿去查占用的文件：``path`` 是文件就是它自己，是目录就在里面挑一批。"""

    try:
        if path.is_file():
            return [path]
        if not path.is_dir():
            return []
        found: list[Path] = []
        visited = 0
        for current_raw, directory_names, file_names in os.walk(
            path, followlinks=False
        ):
            current = Path(current_raw)
            directory_names[:] = [
                name
                for name in directory_names
                if not _is_link(current / name) and name != "__pycache__"
            ]
            for name in file_names:
                visited += 1
                if Path(name).suffix.lower() in _CANDIDATE_SUFFIXES:
                    found.append(current / name)
                    if len(found) >= _MAX_CANDIDATES:
                        return found
            visited += len(directory_names)
            if visited >= _MAX_VISITED:
                break
        return found
    except Exception:  # noqa: BLE001 - best effort
        return []


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True


def find_file_lockers(paths: Iterable[Path]) -> list[tuple[str, int]]:
    """打开着这些文件的进程 ``[(进程名, pid), ...]``；任何失败都返回空。"""

    if sys.platform != "win32":
        return []
    try:
        names = [str(path) for path in paths]
        if not names:
            return []
        return _restart_manager_lockers(names)
    except Exception:  # noqa: BLE001 - best effort
        return []


def describe_lockers(error: BaseException) -> str:
    """``error`` 是文件被占用 / 拒绝访问时，返回「占用者：a.exe（pid 1）、…」，否则空串。

    rename 的两个路径都查（``filename`` / ``filename2``）；只在 Windows 上、只对拒绝访问与
    共享冲突这几种错误查。"""

    try:
        if sys.platform != "win32" or not isinstance(error, OSError):
            return ""
        if getattr(error, "winerror", None) not in _LOCK_WINERRORS:
            return ""
        candidates: list[Path] = []
        for raw in (error.filename, error.filename2):
            if raw:
                candidates.extend(lock_candidates(Path(os.fsdecode(raw))))
        lockers = find_file_lockers(candidates[:_MAX_CANDIDATES])
        if not lockers:
            return ""
        shown = "、".join(f"{name}（pid {pid}）" for name, pid in lockers[:_MAX_LISTED])
        more = f" 等 {len(lockers)} 个进程" if len(lockers) > _MAX_LISTED else ""
        return f"占用者：{shown}{more}"
    except Exception:  # noqa: BLE001 - best effort
        return ""


def _restart_manager_lockers(names: Sequence[str]) -> list[tuple[str, int]]:
    import ctypes
    from ctypes import wintypes

    class _FileTime(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class _UniqueProcess(ctypes.Structure):
        _fields_ = [
            ("dwProcessId", wintypes.DWORD),
            ("ProcessStartTime", _FileTime),
        ]

    class _ProcessInfo(ctypes.Structure):
        _fields_ = [
            ("Process", _UniqueProcess),
            ("strAppName", wintypes.WCHAR * 256),  # CCH_RM_MAX_APP_NAME + 1
            ("strServiceShortName", wintypes.WCHAR * 64),  # CCH_RM_MAX_SVC_NAME + 1
            ("ApplicationType", ctypes.c_int),
            ("AppStatus", wintypes.ULONG),
            ("TSSessionId", wintypes.DWORD),
            ("bRestartable", wintypes.BOOL),
        ]

    rstrtmgr = ctypes.WinDLL("rstrtmgr", use_last_error=True)
    start_session = rstrtmgr.RmStartSession
    start_session.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        wintypes.LPWSTR,
    ]
    start_session.restype = wintypes.DWORD
    register = rstrtmgr.RmRegisterResources
    register.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        ctypes.POINTER(wintypes.LPCWSTR),
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.c_void_p,
    ]
    register.restype = wintypes.DWORD
    get_list = rstrtmgr.RmGetList
    get_list.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(_ProcessInfo),
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_list.restype = wintypes.DWORD
    end_session = rstrtmgr.RmEndSession
    end_session.argtypes = [wintypes.DWORD]
    end_session.restype = wintypes.DWORD

    session = wintypes.DWORD(0)
    key = ctypes.create_unicode_buffer(33)  # CCH_RM_SESSION_KEY + 1
    if start_session(ctypes.byref(session), 0, key) != 0:
        return []
    try:
        files = (wintypes.LPCWSTR * len(names))(*names)
        if register(session, len(names), files, 0, None, 0, None) != 0:
            return []
        needed = wintypes.UINT(0)
        count = wintypes.UINT(0)
        reasons = wintypes.DWORD(0)
        infos = None
        for _ in range(3):
            # ERROR_MORE_DATA（234）：数组不够大，按 needed 重新分配；进程可能在两次之间增减。
            size = max(int(needed.value), 1)
            infos = (_ProcessInfo * size)()
            count = wintypes.UINT(size)
            status = get_list(
                session,
                ctypes.byref(needed),
                ctypes.byref(count),
                infos,
                ctypes.byref(reasons),
            )
            if status == 0:
                break
            if status != 234:
                return []
        else:
            return []
        lockers: list[tuple[str, int]] = []
        seen: set[int] = set()
        for index in range(int(count.value)):
            info = infos[index]
            pid = int(info.Process.dwProcessId)
            if pid in seen:
                continue
            seen.add(pid)
            lockers.append((_process_name(pid) or info.strAppName or "?", pid))
        return lockers
    finally:
        end_session(session)


def _process_name(pid: int) -> str:
    try:
        import psutil

        return str(psutil.Process(pid).name())
    except Exception:  # noqa: BLE001 - 进程已退出、没权限、没装 psutil
        return ""
