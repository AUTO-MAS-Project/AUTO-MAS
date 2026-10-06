"""uv 工具链：查找、镜像、装卸包。

uv 安装由 Runtime 负责；后端只查找并用 ``ProcessRunner`` 调用。
成功镜像持久化到 ``Config.setting.uv.preferred_mirror``（UI 隐藏）。
升版预检见同包 ``precheck``。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from app.utils import ProcessRunner, get_logger

from ..errors import PluginError

logger = get_logger("插件 uv")

# ── PyPI simple 镜像（顺序即优先级）──
_MIRRORS: list[str] = [
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://pypi.mirrors.ustc.edu.cn/simple/",
    "https://pypi.org/simple/",
]


def ensure() -> str:
    """返回可用的 uv 路径；找不到则报错（不下载、不安装）。

    查找顺序：``AUTO_MAS_UV_EXE`` → ``runtime/tools/uv/<ver>/uv[.exe]`` → PATH。
    """
    env = (os.environ.get("AUTO_MAS_UV_EXE") or "").strip()
    if env and Path(env).is_file():
        return env

    tools = Path.cwd() / "runtime" / "tools" / "uv"
    if tools.is_dir():
        name = "uv.exe" if sys.platform == "win32" else "uv"
        found: list[Path] = []
        for child in tools.iterdir():
            if not child.is_dir():
                continue
            exe = child / name
            if exe.is_file():
                found.append(exe)
        if found:
            path = str(sorted(found, key=lambda p: p.parent.name)[-1])
            os.environ["AUTO_MAS_UV_EXE"] = path
            return path

    uv_path = shutil.which("uv")
    if not uv_path:
        raise PluginError(
            "未找到 uv：请通过 AUTO-MAS-Runtime 安装，或在系统 PATH 中提供 uv"
        )
    os.environ["AUTO_MAS_UV_EXE"] = uv_path
    return uv_path


def site_dir() -> Path:
    """``plugins/pypi/site-packages``，并加入 ``sys.path``。"""
    path = Path.cwd() / "plugins" / "pypi" / "site-packages"
    path.mkdir(parents=True, exist_ok=True)
    text = str(path.resolve())
    if text not in sys.path:
        sys.path.insert(0, text)
    return path


def candidates() -> list[str]:
    """当前候选 ``--index-url``；已验证成功的镜像置顶且无重复。"""
    from app.core.config import Config

    preferred = Config.setting.uv.preferred_mirror or _MIRRORS[0]
    return list(dict.fromkeys([preferred, *_MIRRORS]))


async def mark_ok(mirror_url: str) -> None:
    """某镜像成功后置顶，并持久化到 ``Config.setting.uv.preferred_mirror``。"""
    needle = mirror_url.rstrip("/")
    if not any(url.rstrip("/") == needle for url in _MIRRORS):
        return

    from app.core.config import Config

    current = (Config.setting.uv.preferred_mirror or _MIRRORS[0]).rstrip("/")
    if current == needle:
        return

    Config.setting.uv.preferred_mirror = mirror_url
    await Config.setting.commit()


async def install(package_spec: str, *, dry_run: bool = False) -> None:
    """``uv pip install`` 到共享 site-packages；自动轮替镜像。"""
    target = site_dir()
    last_err = ""
    for mirror_url in candidates():
        args = [
            "install",
            package_spec,
            "--python",
            sys.executable,
            "--target",
            str(target),
            "--index-url",
            mirror_url,
        ]
        if dry_run:
            args.append("--dry-run")
        result = await ProcessRunner.run_process(
            ensure(), "pip", *args, timeout=600
        )
        if result.returncode == 0:
            await mark_ok(mirror_url)
            logger.info(f"uv 安装成功: {package_spec}")
            return
        last_err = (result.stderr or result.stdout or "")[-2000:]
        logger.debug(f"uv 安装镜像失败: {mirror_url}: {last_err[-200:]}")
    raise PluginError(
        f"uv 安装失败（已尝试全部镜像）: {package_spec}",
        payload={"stderr": last_err},
    )


async def uninstall(package_name: str) -> None:
    """``uv pip uninstall``（目标目录）。"""
    target = site_dir()
    result = await ProcessRunner.run_process(
        ensure(),
        "pip",
        "uninstall",
        package_name,
        "--python",
        sys.executable,
        "--target",
        str(target),
        timeout=300,
    )
    if result.returncode != 0:
        logger.error(f"uv 卸载失败: {package_name}")
        raise PluginError(
            f"uv 卸载失败: {package_name}",
            payload={
                "stdout": (result.stdout or "")[-2000:],
                "stderr": (result.stderr or "")[-2000:],
            },
        )
    logger.info(f"uv 卸载成功: {package_name}")
