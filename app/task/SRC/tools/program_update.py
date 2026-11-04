# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SRC Git 更新：独立对象库预取，停机后快进代码并复用原生安装器准备依赖。"""

import asyncio
import re
import shutil
import stat
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import psutil

from app.core import Config
from app.services import script_install
from app.utils import io as io_utils

from .poor_yaml import poor_yaml_read, poor_yaml_write


@dataclass(frozen=True)
class PreparedUpdate:
    root: Path
    base_commit: str
    target_commit: str
    repository: str
    branch: str
    git: str
    objects: Path
    python: Path


def assert_idle(root: Path, *, allow_background_adb: bool = False) -> None:
    root = root.resolve()
    for process in psutil.process_iter(["exe", "name"]):
        try:
            exe = process.info["exe"]
            if not exe and str(process.info.get("name", "")).casefold() == "src.exe":
                raise script_install.InstallUnsafeError(
                    "无法确认 SRC 已退出，请以管理员身份重试"
                )
            if exe and Path(exe).resolve().is_relative_to(root):
                candidate = Path(exe).resolve()
                if allow_background_adb and candidate.name.casefold() == "adb.exe":
                    continue
                raise script_install.InstallUnsafeError(
                    "SRC 或其子程序仍在运行，请退出后重试"
                )
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise script_install.InstallUnsafeError(
                "无法确认 SRC 进程状态，请以管理员身份重试"
            ) from error


async def command(
    *args: str, cwd: Path, writing: bool = False, timeout: float = 1800
) -> str:
    """下载取消可停止子进程；写盘阶段取消时等待原生操作退出，不放行安装目录。"""
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    work = asyncio.create_task(process.communicate())
    try:
        output, _ = await asyncio.wait_for(asyncio.shield(work), timeout)
    except (asyncio.CancelledError, TimeoutError):
        if not writing and process.returncode is None:
            process.kill()
        # 安装器会写代码/依赖，不在它仍运行时释放目录锁。
        while not work.done():
            try:
                await asyncio.shield(work)
            except asyncio.CancelledError:
                continue
        raise
    if process.returncode:
        if writing:
            raise script_install.InstallUnsafeError(
                "SRC 原生更新未完成，请保留安装现场并重试或手动修复"
            )
        raise ValueError("SRC 更新检查或下载失败，请检查原生代码源和网络设置")
    return output.decode("utf-8", errors="replace").strip()


def read_deploy(root: Path) -> dict:
    return poor_yaml_read(root / "config/deploy.yaml")


def git_executable(root: Path, deploy: dict) -> str:
    configured = str(deploy.get("GitExecutable") or "./toolkit/Git/mingw64/bin/git.exe")
    path = root / configured
    if path.is_file():
        return str(path.resolve())
    executable = shutil.which("git")
    if executable:
        return executable
    raise ValueError("未找到 SRC 原生 Git，请先完成 SRC 安装")


async def prepare_update(root: Path) -> PreparedUpdate | None:
    """只读部署偏好和当前提交，网络对象下载到 MAS 缓存，不修改原安装的 .git。"""
    root = root.resolve()
    deploy = await asyncio.to_thread(read_deploy, root)
    git = git_executable(root, deploy)
    repository = str(deploy.get("Repository") or "cn")
    if repository in {"cn", "global"}:
        repository = "https://github.com/LmeSzinc/StarRailCopilot"
    parsed = urlsplit(repository)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("SRC 托管更新仅支持无内嵌凭据的 HTTPS 代码源")
    branch = str(deploy.get("Branch") or "master")
    await command(git, "check-ref-format", "--branch", branch, cwd=root)
    base = await command(git, "rev-parse", "HEAD", cwd=root)
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("无法识别 SRC 当前 Git 提交")
    if await command(
        git,
        "--no-optional-locks",
        "status",
        "--porcelain",
        "--untracked-files=no",
        cwd=root,
    ):
        raise ValueError("SRC 程序文件有本地修改，未自动覆盖，请在原生界面处理")
    python = root / str(deploy.get("PythonExecutable") or "./toolkit/python.exe")
    if not python.is_file() or not (root / "installer.py").is_file():
        raise ValueError("SRC 原生 Python 或安装器缺失，请先完成官方安装")
    cache = Config.data_path / "src_update"
    cache.mkdir(parents=True, exist_ok=True)
    objects = Path(tempfile.mkdtemp(prefix="git-", dir=cache))
    await command(git, "init", "--bare", str(objects), cwd=cache)
    proxy = str(deploy.get("GitProxy") or "").strip()
    # 原生 GitProxy 优先；配置中的代理只传给子进程，不进入日志或任务身份。
    await command(
        git,
        "-c",
        f"http.proxy={proxy}",
        "-c",
        "http.sslVerify=true",
        "fetch",
        "--no-tags",
        "--",
        repository,
        branch,
        cwd=objects,
    )
    target = await command(git, "rev-parse", "FETCH_HEAD", cwd=objects)
    if not re.fullmatch(r"[0-9a-f]{40}", target):
        raise ValueError("SRC 下载结果不是可识别的 Git 提交")
    await command(git, "merge-base", "--is-ancestor", base, target, cwd=objects)
    if (
        base == target
        and not (script_install.workspace(root) / "src-install.json").exists()
    ):
        shutil.rmtree(objects)
        return None
    return PreparedUpdate(
        root, base, target, repository, branch, git, objects, python.resolve()
    )


def remove_cached_git_objects(objects: Path) -> None:
    """Windows Git 对象通常只读；成功安装后的缓存清理不能使安装失败。"""

    def make_writable(func, path, exc):
        try:
            Path(path).chmod(Path(path).stat().st_mode | stat.S_IWRITE)
            func(path)
        except OSError:
            raise exc[1]

    try:
        shutil.rmtree(objects, onerror=make_writable)
    except OSError as error:
        warnings.warn(f"SRC 已安装成功，但无法清理 Git 预下载缓存 {objects}: {error}")


def assert_safe_to_launch(root: Path) -> None:
    """不触网的统一启动门禁；运行前先恢复临时部署设置。"""
    recover_deploy(root)
    marker = script_install.workspace(root) / "src-install.json"
    if marker.exists():
        raise script_install.InstallUnsafeError(
            "SRC 上次更新尚未确认，禁止启动原生界面或自动代理"
        )


def recover_deploy(root: Path) -> None:
    journal = script_install.workspace(root) / "src-deploy.json"
    if not journal.exists():
        return
    assert_idle(root, allow_background_adb=True)
    state = io_utils.read_dict_file(journal)
    if state["root"] != str(root.resolve()):
        raise script_install.InstallUnsafeError(
            "SRC 更新配置恢复记录归属不符，请保留现场"
        )
    current = read_deploy(root)
    restored = {
        key: state["original"][key]
        for key, value in state["injected"].items()
        if current.get(key) == value
    }
    poor_yaml_write(restored, root / "config/deploy.yaml")
    journal.unlink()


async def confirm_current_install(root: Path) -> None:
    await asyncio.to_thread(assert_idle, root, allow_background_adb=True)
    if (script_install.workspace(root) / "src-install.json").exists():
        raise script_install.InstallUnsafeError(
            "SRC 上次代码或依赖安装未确认，请开启更新托管重试或手动修复"
        )
    if not (root / "src.exe").is_file() or not (root / "installer.py").is_file():
        raise script_install.InstallUnsafeError("SRC 当前安装不完整，请先完成官方安装")


async def apply_update(root: Path, prepared: PreparedUpdate) -> None:
    """持安装锁调用。预下载失效或存在本地修改时不覆盖用户程序。"""
    if root.resolve() != prepared.root:
        raise ValueError("SRC 预下载属于另一个安装目录")
    await asyncio.to_thread(assert_idle, root)
    deploy = await asyncio.to_thread(read_deploy, root)
    repository = str(deploy.get("Repository") or "cn")
    if repository in {"cn", "global"}:
        repository = "https://github.com/LmeSzinc/StarRailCopilot"
    if (
        repository != prepared.repository
        or str(deploy.get("Branch") or "master") != prepared.branch
    ):
        raise ValueError("SRC 代码源在预下载后变更，请重新检查更新")
    current = await command(prepared.git, "rev-parse", "HEAD", cwd=root)
    if current != prepared.base_commit or await command(
        prepared.git,
        "--no-optional-locks",
        "status",
        "--porcelain",
        "--untracked-files=no",
        cwd=root,
    ):
        raise ValueError("SRC 安装在预下载后发生变化，请重新检查更新")
    directory = script_install.workspace(root)
    directory.mkdir(parents=True, exist_ok=True)
    journal = directory / "src-deploy.json"
    if journal.exists():
        raise script_install.InstallUnsafeError("SRC 上次更新配置尚未恢复")
    # 原生安装器负责依赖、app.asar 和 ADB；Git 步骤已由 MAS 准备并快进。
    injected = {
        key: value
        for key, value in {"AutoUpdate": False, "EnableReload": False}.items()
        if key in deploy
    }
    if "AutoUpdate" not in injected:
        raise ValueError("SRC 部署配置缺少原生 AutoUpdate 开关，不能安全接管")
    io_utils.write_file(
        journal, {"root": str(root.resolve()), "original": deploy, "injected": injected}
    )
    marker = directory / "src-install.json"
    try:
        poor_yaml_write(injected, root / "config/deploy.yaml")
        # 从本地对象库导入，不重新访问远端；失败前尚未切换工作区。
        await command(
            prepared.git,
            "fetch",
            "--no-tags",
            str(prepared.objects),
            prepared.target_commit,
            cwd=root,
        )
        io_utils.write_file(marker, {"target": prepared.target_commit})
        await command(
            prepared.git,
            "merge",
            "--ff-only",
            prepared.target_commit,
            cwd=root,
            writing=True,
        )
        await command(str(prepared.python), "installer.py", cwd=root, writing=True)
        if (
            await command(prepared.git, "rev-parse", "HEAD", cwd=root)
            != prepared.target_commit
        ):
            raise script_install.InstallUnsafeError("SRC 安装后提交未确认，请手动修复")
        marker.unlink()
    finally:
        # 原生安装器已退出后撤销临时部署设置，失败标记不随配置恢复被删除。
        recover_deploy(root)
    remove_cached_git_objects(prepared.objects)


async def update_before_run(root: Path) -> str:
    recover_deploy(root)
    candidate = await prepare_update(root)
    if candidate is not None:
        await apply_update(root, candidate)
    await confirm_current_install(root)
    return "SRC 本体更新准备完成，原生依赖安装器已处理或当前无需更新"
