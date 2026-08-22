"""主程序 core 升版预检：uv dry-run 判定已装插件与拟定 core 能否共解。"""

from __future__ import annotations

import re
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

from packaging.version import InvalidVersion, Version

from app.utils.tools import to_pep440

from ..errors import VersionConflict
from ..types import CORE_DISTRIBUTION_NAME, CORE_PLUGIN_NAME
from . import mirrors
from .tool import pip

if TYPE_CHECKING:
    from app.models.config import PluginRecord


@dataclass(frozen=True)
class CoreCompat:
    """单插件与拟定 core 的 dry-run 结果。"""

    ok: bool
    required: str = ""
    detail: str = ""


async def check_core(
    *,
    package: str | None = None,
    version: str | None = None,
    path: Path | None = None,
    core_version: str,
) -> CoreCompat:
    """``uv pip install --dry-run``：插件与 ``auto-mas-core==core_version`` 能否共解。

    - 本地造 stub wheel，经 ``--find-links`` 注入（不发 PyPI）。
    - 目标：``package==version`` 或本地 ``path``（pyproject 工程）。
    - 解析成功且会安装 core → 兼容；成功但不含 core → 未声明；失败 → 不兼容。
    """
    core_ver = (core_version or "").strip()
    if not core_ver:
        return CoreCompat(ok=False, required="(bad-core)", detail="空的 core 版本")

    if path is not None:
        target_spec = str(path.resolve())
    else:
        pkg = (package or "").strip()
        ver = (version or "").strip()
        if not pkg or not ver:
            return CoreCompat(
                ok=False, required="(unknown)", detail="缺少发行包名或已装版本"
            )
        target_spec = f"{pkg}=={ver}"

    with tempfile.TemporaryDirectory(prefix="auto-mas-core-check-") as tmp:
        tmp_path = Path(tmp)
        links = tmp_path / "links"
        links.mkdir()
        empty = tmp_path / "target"
        empty.mkdir()

        # ── 最小 stub wheel，供解析器拿到拟定的新 core 版本 ──
        safe = CORE_DISTRIBUTION_NAME.replace("-", "_")
        wheel_name = f"{safe}-{core_ver}-py3-none-any.whl"
        dist_info = f"{safe}-{core_ver}.dist-info"
        with ZipFile(links / wheel_name, "w", ZIP_DEFLATED) as zf:
            zf.writestr(
                f"{dist_info}/METADATA",
                "\n".join(
                    [
                        "Metadata-Version: 2.1",
                        f"Name: {CORE_DISTRIBUTION_NAME}",
                        f"Version: {core_ver}",
                        "Summary: AUTO-MAS core stub for precheck",
                        "",
                    ]
                ),
            )
            zf.writestr(
                f"{dist_info}/WHEEL",
                "Wheel-Version: 1.0\nGenerator: auto-mas\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr(f"{safe}/__init__.py", "")

        last_err = ""
        for mirror_url in mirrors.candidates():
            result = await pip(
                "install",
                target_spec,
                "--dry-run",
                "--python",
                sys.executable,
                "--target",
                str(empty),
                "--find-links",
                str(links),
                "--prerelease",
                "allow",
                "--index-url",
                mirror_url,
                timeout=180,
            )
            out = f"{result.stdout or ''}\n{result.stderr or ''}"
            if result.returncode != 0:
                last_err = out[-2000:]
                if re.search(r"No solution|because|incompatible|conflict", out, re.I):
                    await mirrors.mark_ok(mirror_url)
                    return CoreCompat(
                        ok=False,
                        required=CORE_DISTRIBUTION_NAME,
                        detail=last_err.strip()[-500:]
                        or "uv 解析失败：与拟定 core 不兼容",
                    )
                continue

            await mirrors.mark_ok(mirror_url)
            if re.search(rf"[+\s]{re.escape(CORE_DISTRIBUTION_NAME)}==", out):
                return CoreCompat(ok=True)
            return CoreCompat(
                ok=False,
                required="(undeclared)",
                detail="未声明 auto-mas-core 依赖，无法确认兼容",
            )

        return CoreCompat(
            ok=False,
            required="(fetch-failed)",
            detail=last_err.strip()[-500:] or "uv dry-run 全部镜像失败",
        )


async def precheck_core_bump(
    new_version: str,
    *,
    plugins: Iterable[PluginRecord],
) -> list[VersionConflict]:
    """对注册表插件逐个 ``check_core``；空列表 = 通过。"""
    try:
        pep = str(Version(new_version))
    except InvalidVersion:
        pep = to_pep440(new_version)
    conflicts: list[VersionConflict] = []

    for record in sorted(plugins, key=lambda r: r.info.plugin_name or ""):
        name = record.info.plugin_name
        if not name or name == CORE_PLUGIN_NAME:
            continue
        package = (record.info.package_name or "").strip() or None
        installed_ver = (record.info.version or "").strip() or None

        # ── 选定 dry-run 目标：优先钉死已装版本的发行包，否则本地路径 ──
        if package and installed_ver:
            result = await check_core(
                package=package,
                version=installed_ver,
                core_version=pep,
            )
        elif record.info.source == "local" and record._project_dir is not None:
            root = record._project_dir
            if not (root / "pyproject.toml").is_file():
                root = root.parent
            if not (root / "pyproject.toml").is_file():
                conflicts.append(
                    VersionConflict(
                        plugin_name=name,
                        distribution=CORE_DISTRIBUTION_NAME,
                        required="(unknown)",
                        proposed=pep,
                        message=f"插件 `{name}` 无发行版本且找不到本地 pyproject，无法预检",
                    )
                )
                continue
            result = await check_core(path=root, core_version=pep)
        else:
            conflicts.append(
                VersionConflict(
                    plugin_name=name,
                    distribution=CORE_DISTRIBUTION_NAME,
                    required="(unknown)",
                    proposed=pep,
                    message=f"插件 `{name}` 无发行包名/版本，无法经 uv 预检",
                )
            )
            continue

        if result.ok:
            continue
        conflicts.append(
            VersionConflict(
                plugin_name=name,
                distribution=CORE_DISTRIBUTION_NAME,
                required=result.required or "(conflict)",
                proposed=pep,
                message=f"插件 `{name}` 与核心 {pep} 不兼容：{result.detail}",
            )
        )
    return conflicts
