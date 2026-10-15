"""以真实鹰角启动器为父进程启动终末地，也供 MXU 前置程序独立调用。

临时补位：MaaEnd #6457 尚未提供 PC 启动入口；上游提供后改为调用并移除。
启动方式参考 AliceJump/ok-end-field#520，不修改游戏文件或启动参数。
"""

import argparse
import ctypes
import json
import logging
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import psutil

logger = logging.getLogger("终末地启动")

# 当前官方启动器签名，证书轮换后需同步更新（与参考实现保持一致）。
_OFFICIAL_SIGNERS = {
    "2B366F397E64A9494A553B70004E8CA1AAE02B9D",
    "FF4AF264C36A27F0C805936708EF8EC67B396225",
}
_LAUNCHER_TIMEOUT = 30
_PROCESS_CREATE_PROCESS = 0x0080
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", wintypes.LPVOID)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "OpenProcess": (
            [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
            wintypes.HANDLE,
        ),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "QueryFullProcessImageNameW": (
            [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ],
            wintypes.BOOL,
        ),
        "InitializeProcThreadAttributeList": (
            [
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(ctypes.c_size_t),
            ],
            wintypes.BOOL,
        ),
        "UpdateProcThreadAttribute": (
            [
                wintypes.LPVOID,
                wintypes.DWORD,
                ctypes.c_size_t,
                wintypes.LPVOID,
                ctypes.c_size_t,
                wintypes.LPVOID,
                wintypes.LPVOID,
            ],
            wintypes.BOOL,
        ),
        "DeleteProcThreadAttributeList": ([wintypes.LPVOID], None),
        "CreateProcessW": (
            [
                wintypes.LPCWSTR,
                wintypes.LPWSTR,
                wintypes.LPVOID,
                wintypes.LPVOID,
                wintypes.BOOL,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.LPCWSTR,
                ctypes.POINTER(_StartupInfoEx),
                ctypes.POINTER(_ProcessInfo),
            ],
            wintypes.BOOL,
        ),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = args
        function.restype = result
    return kernel


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


def _verify_launcher(path: Path) -> None:
    """通过系统 Authenticode 校验官方签名；路径通过环境变量传递。"""
    powershell = Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0"
    result = subprocess.run(
        [
            str(powershell / "powershell.exe"),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$ErrorActionPreference='Stop'; "
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            "$s=Get-AuthenticodeSignature -LiteralPath $env:MAS_ENDFIELD_LAUNCHER; "
            "@{status=[int]$s.Status; signer=$s.SignerCertificate.Thumbprint} "
            "| ConvertTo-Json -Compress",
        ],
        env={
            **os.environ,
            "MAS_ENDFIELD_LAUNCHER": str(path),
            "PSModulePath": str(powershell / "Modules"),
        },
        capture_output=True,
        text=True,
        encoding="utf-8-sig",
        errors="replace",
        timeout=15,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    signature = json.loads(result.stdout)
    if (
        signature.get("status") != 0
        or (signature.get("signer") or "").upper() not in _OFFICIAL_SIGNERS
    ):
        raise RuntimeError(f"鹰角启动器签名校验失败，请重新选择官方启动器: {path}")


def _game_running(game_path: Path) -> bool:
    for process in psutil.process_iter(["exe"]):
        try:
            if process.info["exe"] and Path(process.info["exe"]) == game_path:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _find_parent(kernel, launcher_path: Path):
    """核验同一安装目录下的 Games.exe，返回保持打开的父进程句柄。"""
    for process in psutil.process_iter(["name"]):
        if (process.info["name"] or "").lower() != "games.exe":
            continue
        handle = None
        try:
            handle = _check(
                kernel.OpenProcess(
                    _PROCESS_CREATE_PROCESS | _PROCESS_QUERY_LIMITED_INFORMATION,
                    False,
                    process.pid,
                )
            )
            image = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(image))
            _check(
                kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size))
            )
            image_path = Path(image.value).resolve()
            if image_path.name.lower() != "games.exe" or not (
                image_path == launcher_path
                if launcher_path.name.lower() == "games.exe"
                else image_path.is_relative_to(launcher_path.parent)
            ):
                continue
            _verify_launcher(image_path)
            logger.info("官方启动器已就绪: PID=%s, %s", process.pid, image_path)
            parent = handle
            handle = None
            return parent
        except psutil.NoSuchProcess:
            continue
        except OSError as error:
            # 枚举后退出的进程可跳过，权限问题需明确报错。
            if not psutil.pid_exists(process.pid):
                continue
            raise RuntimeError(
                f"无法访问鹰角启动器，请检查启动器权限: {error}"
            ) from error
        finally:
            if handle:
                kernel.CloseHandle(handle)
    return None


def _prepare_launcher(kernel, launcher_path: Path):
    parent = _find_parent(kernel, launcher_path)
    if parent:
        return parent
    _verify_launcher(launcher_path)
    logger.info("启动鹰角启动器: %s", launcher_path)
    args = [str(launcher_path)]
    if launcher_path.name.lower() == "launcher.exe":
        args.extend(["--game=Endfield", "--reason=4"])
    subprocess.Popen(
        args,
        cwd=launcher_path.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    deadline = time.monotonic() + _LAUNCHER_TIMEOUT
    while time.monotonic() < deadline:
        parent = _find_parent(kernel, launcher_path)
        if parent:
            return parent
        time.sleep(0.25)
    raise TimeoutError("鹰角启动器在 30 秒内未就绪，请检查启动器是否能正常打开")


def _create_game(kernel, game_path: Path, arguments: str, parent) -> int:
    size = ctypes.c_size_t()
    kernel.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(size.value)
    attributes = ctypes.cast(buffer, wintypes.LPVOID)
    _check(
        kernel.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size))
    )
    try:
        parent_handle = wintypes.HANDLE(parent)
        _check(
            kernel.UpdateProcThreadAttribute(
                attributes,
                0,
                _PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
                ctypes.byref(parent_handle),
                ctypes.sizeof(parent_handle),
                None,
                None,
            )
        )
        startup = _StartupInfoEx()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.lpAttributeList = attributes
        process = _ProcessInfo()
        # 仅转义可执行文件路径，用户填写的 Windows 参数原样传递。
        command = ctypes.create_unicode_buffer(
            subprocess.list2cmdline([str(game_path)])
            + (" " + arguments if arguments else "")
        )
        _check(
            kernel.CreateProcessW(
                str(game_path),
                command,
                None,
                None,
                False,
                _EXTENDED_STARTUPINFO_PRESENT | subprocess.CREATE_NO_WINDOW,
                None,
                str(game_path.parent),
                ctypes.byref(startup),
                ctypes.byref(process),
            )
        )
        try:
            return process.dwProcessId
        finally:
            kernel.CloseHandle(process.hThread)
            kernel.CloseHandle(process.hProcess)
    finally:
        kernel.DeleteProcThreadAttributeList(attributes)


def launch_game(launcher_path: Path, game_path: Path, arguments: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("鹰角启动器启动终末地仅支持 Windows")
    game_path = game_path.resolve()
    launcher_path = launcher_path.resolve()
    if _game_running(game_path):
        logger.info("终末地已运行，跳过启动")
        return
    if not launcher_path.is_file() or launcher_path.name.lower() not in {
        "launcher.exe",
        "games.exe",
    }:
        raise ValueError("请在游戏设置中选择鹰角官方启动器 Launcher.exe 或 Games.exe")
    if not game_path.is_file():
        raise FileNotFoundError("请在游戏设置中选择 Endfield.exe")
    kernel = _kernel32()
    parent = _prepare_launcher(kernel, launcher_path)
    try:
        if not _game_running(game_path):
            pid = _create_game(kernel, game_path, arguments, parent)
            logger.info("已通过官方启动器父进程启动终末地: PID=%s", pid)
    finally:
        kernel.CloseHandle(parent)


def main() -> int:
    parser = argparse.ArgumentParser(description="AUTO-MAS 终末地启动入口")
    parser.add_argument("launcher", type=Path)
    parser.add_argument("game", type=Path)
    parser.add_argument("--arguments", default="")
    parser.add_argument("--result-file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stdout
    )
    error_message = None
    try:
        launch_game(args.launcher, args.game, args.arguments)
    except Exception as error:
        error_message = str(error)
        logger.exception("终末地启动失败: %s", error)
    if args.result_file:
        # MXU 会丢弃前置程序的标准流，单独回传 MAS 自有启动结果。
        args.result_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.result_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"error": error_message}), encoding="utf-8")
        temporary.replace(args.result_file)
    return 1 if error_message is not None else 0


if __name__ == "__main__":
    sys.exit(main())
