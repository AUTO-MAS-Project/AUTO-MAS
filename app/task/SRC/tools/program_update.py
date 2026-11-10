# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SRC Git 更新：独立对象库预取，停机后快进代码并复用原生安装器准备依赖。"""

import asyncio
import json
import re
import shutil
import stat
import tempfile
import warnings
import zipfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil

from app.core import Config
from app.services import script_install
from app.utils import io as io_utils
from app.utils.common.process.runner import (
    create_subprocess,
    is_process_cleanup_unconfirmed,
    observe_process_exit,
    stop_process,
    wait_for_process_cleanup,
)

from .poor_yaml import poor_yaml_read, poor_yaml_write

_WRITE_CLEANUP_SECONDS = 5


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
    script_install.assert_no_pending_process(root)
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
    """更新取消先限时等待，确认点结束后由任务统一强杀，目录保持互斥。"""
    process = await create_subprocess(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    work = asyncio.create_task(process.communicate())
    try:
        output, _ = await asyncio.wait_for(asyncio.shield(work), timeout)
    except (asyncio.CancelledError, TimeoutError) as original:
        if not writing:
            work.cancel()
            with suppress(asyncio.CancelledError):
                await work
            try:
                await stop_process(process, kill_tree=True)
            except BaseException as error:
                if is_process_cleanup_unconfirmed(error):
                    script_install.defer_installation_release(cwd)
                raise
            raise
        try:
            await wait_for_process_cleanup(work, timeout=_WRITE_CLEANUP_SECONDS)
        except asyncio.CancelledError:
            script_install.defer_installation_release(
                cwd, observe_process_exit(process, after_task_cleanup=True)
            )
            raise
        except TimeoutError as error:
            script_install.defer_installation_release(
                cwd, observe_process_exit(process, after_task_cleanup=True)
            )
            failure = script_install.InstallUnsafeError(
                "SRC 更新进程尚未退出，任务已停止等待，安装目录将保持占用直至进程结束"
            )
            if isinstance(original, asyncio.CancelledError):
                raise original from failure
            raise failure from error
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


CN_GIT_OVER_CDN = (
    "https://vip.123pan.cn/1815343254/pack/LmeSzinc_StarRailCopilot_master",
    "https://1815343254.v.123yx.com/1815343254/pack/LmeSzinc_StarRailCopilot_master",
)


async def request_cn_latest() -> tuple[str, str]:
    """按 SRC 上游定义的 Git-over-CDN 协议选择可用节点。"""
    async with httpx.AsyncClient(
        proxy=getattr(Config, "proxy", None),
        timeout=15,
        follow_redirects=True,
    ) as client:
        for url in CN_GIT_OVER_CDN:
            try:
                response = await client.get(f"{url}/latest.json")
                response.raise_for_status()
                data = response.json()
                commit = data["commit"]
                if re.fullmatch(r"[0-9a-f]{40}", commit):
                    return url, commit
            except (httpx.HTTPError, KeyError, ValueError, TypeError):
                continue
    raise ValueError("SRC 国内 Git-over-CDN 当前无法获取有效版本，不会回退到 GitHub")


def unpack_cn_git_pack(archive: Path, objects: Path, target: str) -> Path:
    """限制官方 delta ZIP 的文件名和展开大小，校验实际 Git pack 的完整性。"""
    names = {f"pack-{target}.pack", f"pack-{target}.idx"}
    pack_dir = objects / "objects" / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        if set(package.namelist()) != names or len(package.infolist()) != 2:
            raise ValueError("SRC 国内更新 ZIP 不包含完整、唯一的 Git pack/index")
        for name in sorted(names):
            member = package.getinfo(name)
            if (
                member.flag_bits & 1
                or member.file_size <= 0
                or member.file_size > 2 * 1024**3
            ):
                raise ValueError("SRC 国内更新 ZIP 文件大小或加密状态异常")
            with package.open(member) as source, (pack_dir / name).open("xb") as dest:
                shutil.copyfileobj(source, dest, 1024 * 1024)
    return pack_dir / f"pack-{target}.pack"


async def prepare_cn_objects(root: Path, git: str, objects: Path, base: str) -> str:
    """CDN ZIP 只导入 MAS 私有 bare Git，绝不触碰 SRC 工作目录。"""
    url, target = await request_cn_latest()
    if target == base:
        return target
    # 供 Git 校验 delta pack 中对本地已有对象的引用；只读借用源对象库。
    alternate = objects / "objects" / "info" / "alternates"
    alternate.parent.mkdir(parents=True, exist_ok=True)
    alternate.write_text(str((root / ".git" / "objects").resolve()) + "\n")
    archive = objects.parent / f"{objects.name}.zip"
    download_finished = False
    try:
        from app.core.script_update import download_script_package

        await download_script_package(
            f"{url}/{target}/{base}.zip",
            archive,
            source="GitOverCdn",
            timeout=30 * 60,
            proxy=getattr(Config, "proxy", None),
        )
        download_finished = True
        pack = await asyncio.to_thread(unpack_cn_git_pack, archive, objects, target)
        await command(git, "index-pack", str(pack), cwd=objects)
        await command(git, "cat-file", "-e", f"{target}^{{commit}}", cwd=objects)
        return target
    finally:
        # FluxDown 未确认取消时可能仍在写目标 ZIP，不能提前移除文件。
        if download_finished:
            archive.unlink(missing_ok=True)


async def prepare_update(
    root: Path, *, recovery_snapshot: bytes | None = None
) -> PreparedUpdate | None:
    """只读部署偏好和当前提交，网络对象下载到 MAS 缓存，不修改原安装的 .git。"""
    root = root.resolve()
    deploy = await asyncio.to_thread(read_deploy, root)
    git = git_executable(root, deploy)
    repository = str(deploy.get("Repository") or "cn")
    cn_source = repository == "cn"
    if repository == "global":
        repository = "https://github.com/LmeSzinc/StarRailCopilot"
    parsed = urlsplit(repository)
    if not cn_source and (
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

    # 用户主动重试时，若上轮 Git 已快进到目标，仅重新运行原生安装器即可。
    # 不应要求再次从 CDN 获取相同提交（特别是未提供差量包时）。
    if recovery_snapshot is not None:
        record = validate_install_marker(root, recovery_snapshot)
        if record == base:
            objects = Path(tempfile.mkdtemp(prefix="native-repair-", dir=cache))
            return PreparedUpdate(
                root, base, base, repository, branch, git, objects, python.resolve()
            )
    objects = Path(tempfile.mkdtemp(prefix="git-", dir=cache))
    await command(git, "init", "--bare", str(objects), cwd=cache)
    if cn_source:
        if branch != "master":
            raise ValueError("SRC 原生 Git-over-CDN 仅提供 master 分支，请切换代码源")
        target = await prepare_cn_objects(root, git, objects, base)
    else:
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
    # CDN 回报最新且无需增量包时，bare 缓存不包含原 HEAD 对象。
    if not (cn_source and base == target):
        await command(git, "merge-base", "--is-ancestor", base, target, cwd=objects)
    if (
        base == target
        and not (script_install.workspace(root) / "src-install.json").exists()
    ):
        remove_cached_git_objects(objects)
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
    script_install.assert_no_pending_process(root)
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


async def apply_update(
    root: Path,
    prepared: PreparedUpdate,
    *,
    recovery_snapshot: bytes | None = None,
) -> None:
    """持安装锁调用。预下载失效或存在本地修改时不覆盖用户程序。"""
    if root.resolve() != prepared.root:
        raise ValueError("SRC 预下载属于另一个安装目录")
    await asyncio.to_thread(assert_idle, root)
    deploy = await asyncio.to_thread(read_deploy, root)
    repository = str(deploy.get("Repository") or "cn")
    if repository == "global":
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
    # 不能用普通自动更新覆盖上轮的安全标记，只有明确回复的同一标记可被重试。
    if marker.exists() or marker.is_symlink():
        if recovery_snapshot is None:
            raise script_install.InstallUnsafeError(
                "SRC 上轮安装尚未确认，必须由用户决定重试或跳过"
            )
        validate_install_marker(root, recovery_snapshot)
    elif recovery_snapshot is not None:
        raise script_install.InstallUnsafeError("SRC 安装记录已消失，拒绝旧恢复请求")

    try:
        poor_yaml_write(injected, root / "config/deploy.yaml")
        if prepared.base_commit != prepared.target_commit:
            # 从本地对象库导入并快进；当前 HEAD 已是目标时只重跑原生安装器。
            await command(
                prepared.git,
                "fetch",
                "--no-tags",
                str(prepared.objects),
                prepared.target_commit,
                cwd=root,
            )
        if recovery_snapshot is not None:
            validate_install_marker(root, recovery_snapshot)
        io_utils.write_file(marker, {"target": prepared.target_commit})
        if prepared.base_commit != prepared.target_commit:
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
            or not (root / "src.exe").is_file()
            or not (root / "installer.py").is_file()
        ):
            raise script_install.InstallUnsafeError(
                "SRC 原生安装后提交或程序文件尚未确认，保留标记"
            )
        marker.unlink()
    finally:
        # 原生安装器已退出后撤销临时部署设置，失败标记不随配置恢复被删除。
        recover_deploy(root)
    remove_cached_git_objects(prepared.objects)


def validate_install_marker(root: Path, snapshot: bytes) -> str:
    """拒绝符号链接、标记替换和未知 Git commit，避免旧弹窗误授权新安装。"""
    marker = script_install.workspace(root) / "src-install.json"
    if (
        marker.is_symlink()
        or not marker.is_file()
        or len(snapshot) > 64 * 1024
        or marker.read_bytes() != snapshot
    ):
        raise script_install.InstallUnsafeError("SRC 安装标记已经变化，拒绝恢复")
    try:
        record = json.loads(snapshot)
        target = record["target"]
        if not isinstance(target, str) or not re.fullmatch(r"[0-9a-f]{40}", target):
            raise ValueError("not a Git commit")
    except (ValueError, TypeError, KeyError) as error:
        raise script_install.InstallUnsafeError(
            "SRC 安装标记不是有效的 Git 提交记录，无法自动恢复"
        ) from error
    return target


async def skip_unconfirmed_install(root: Path, snapshot: bytes) -> str:
    """仅 Git 提交已达标、工作区干净、Python 依赖可用时允许用户跳过。"""
    recover_deploy(root)
    target = validate_install_marker(root, snapshot)
    await asyncio.to_thread(assert_idle, root, allow_background_adb=True)
    deploy = await asyncio.to_thread(read_deploy, root)
    git = git_executable(root, deploy)
    if (
        await command(git, "rev-parse", "HEAD", cwd=root) != target
        or await command(
            git,
            "--no-optional-locks",
            "status",
            "--porcelain",
            "--untracked-files=no",
            cwd=root,
        )
    ):
        raise script_install.InstallUnsafeError(
            "SRC Git 代码未完整到达上次更新目标或存在修改，不允许跳过"
        )
    python = root / str(deploy.get("PythonExecutable") or "./toolkit/python.exe")
    if not (
        (root / "src.exe").is_file()
        and (root / "installer.py").is_file()
        and python.is_file()
    ):
        raise script_install.InstallUnsafeError(
            "SRC 当前程序或原生依赖安装器缺失，不允许跳过"
        )
    try:
        await command(str(python.resolve()), "-m", "pip", "check", cwd=root)
    except Exception as error:
        raise script_install.InstallUnsafeError(
            "SRC Python 依赖检查失败，不允许跳过，请重试原生安装"
        ) from error
    await asyncio.to_thread(assert_idle, root, allow_background_adb=True)
    validate_install_marker(root, snapshot)
    marker = script_install.workspace(root) / "src-install.json"
    marker.unlink()
    try:
        await confirm_current_install(root)
    except BaseException:
        if not marker.exists() and not marker.is_symlink():
            try:
                marker.write_bytes(snapshot)
            except OSError:
                pass
        raise
    return target[:12]


async def update_before_run(
    root: Path, *, recovery_snapshot: bytes | None = None
) -> str:
    recover_deploy(root)
    if recovery_snapshot is not None:
        validate_install_marker(root, recovery_snapshot)
    candidate = await prepare_update(root, recovery_snapshot=recovery_snapshot)
    if candidate is not None:
        await apply_update(root, candidate, recovery_snapshot=recovery_snapshot)
    await confirm_current_install(root)
    return "SRC 本体更新准备完成，原生依赖安装器已处理或当前无需更新"
