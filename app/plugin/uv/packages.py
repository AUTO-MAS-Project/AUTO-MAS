"""经 uv 装卸包到共享 site-packages。"""

from __future__ import annotations

import sys

from ..errors import PluginError
from . import mirrors
from .tool import pip, site_dir


async def install(package_spec: str, *, dry_run: bool = False) -> None:
    """``uv pip install`` 到共享 site-packages；自动轮替镜像。"""
    target = site_dir()
    last_err = ""
    for mirror_url in mirrors.candidates():
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
        result = await pip(*args, timeout=600)
        if result.returncode == 0:
            await mirrors.mark_ok(mirror_url)
            return
        last_err = (result.stderr or result.stdout or "")[-2000:]
    raise PluginError(
        f"uv 安装失败（已尝试全部镜像）: {package_spec}",
        payload={"stderr": last_err},
    )


async def uninstall(package_name: str) -> None:
    """``uv pip uninstall``（目标目录）。"""
    target = site_dir()
    result = await pip(
        "uninstall",
        package_name,
        "--python",
        sys.executable,
        "--target",
        str(target),
        timeout=300,
    )
    if result.returncode != 0:
        raise PluginError(
            f"uv 卸载失败: {package_name}",
            payload={
                "stdout": (result.stdout or "")[-2000:],
                "stderr": (result.stderr or "")[-2000:],
            },
        )
