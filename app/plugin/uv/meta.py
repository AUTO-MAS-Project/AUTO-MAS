"""经 uv 拉取发行包 METADATA（不手写 PyPI JSON 协议）。"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from email.parser import Parser
from pathlib import Path

from ..errors import PluginError
from . import mirrors
from .tool import pip


@dataclass(frozen=True)
class PackageMeta:
    """``uv pip install --no-deps`` 后从 dist-info/METADATA 解析的字段。"""

    name: str
    version: str
    summary: str = ""
    requires_dist: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    project_urls: dict[str, str] = field(default_factory=dict)


async def fetch(package: str, *, version: str | None = None) -> PackageMeta:
    """经 uv 拉取包元数据：``uv pip install --no-deps`` 到临时目录后解析 METADATA。

    - ``version`` 给定 → 装该版本（对应已装版本预检，而非索引最新版）。
    - ``version`` 省略 → 装索引当前解析到的版本（市场等场景）。
    """
    name = (package or "").strip()
    if not name:
        raise PluginError("空包名无法拉取元数据")
    spec = f"{name}=={version.strip()}" if (version or "").strip() else name

    cache_root = Path.cwd() / "plugins" / "pypi" / "meta-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    safe = name.lower().replace("-", "_")
    ver_key = (version or "").strip() or "latest"
    work = cache_root / f"{safe}@{ver_key}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    last_err = ""
    for mirror_url in mirrors.candidates():
        result = await pip(
            "install",
            spec,
            "--no-deps",
            "--python",
            sys.executable,
            "--target",
            str(work),
            "--index-url",
            mirror_url,
            timeout=600,
        )
        if result.returncode != 0:
            last_err = (result.stderr or result.stdout or "")[-2000:]
            continue
        await mirrors.mark_ok(mirror_url)
        # ── 解析 uv 落下的 METADATA（标准邮件头格式）──
        dist_infos = list(work.glob("*.dist-info"))
        if not dist_infos:
            last_err = "安装成功但未找到 .dist-info"
            continue
        meta_file = dist_infos[0] / "METADATA"
        if not meta_file.is_file():
            last_err = "缺少 METADATA"
            continue
        msg = Parser().parsestr(meta_file.read_text(encoding="utf-8"))
        raw_kw = msg.get("Keywords") or ""
        if "," in raw_kw:
            keywords = [p.strip() for p in raw_kw.split(",") if p.strip()]
        else:
            keywords = [p.strip() for p in raw_kw.split() if p.strip()]
        urls: dict[str, str] = {}
        for item in msg.get_all("Project-URL") or []:
            if "," in item:
                label, url = item.split(",", 1)
                urls[label.strip()] = url.strip()
        return PackageMeta(
            name=str(msg.get("Name") or name),
            version=str(msg.get("Version") or version or ""),
            summary=str(msg.get("Summary") or ""),
            requires_dist=[str(x) for x in (msg.get_all("Requires-Dist") or []) if x],
            keywords=keywords,
            project_urls=urls,
        )

    raise PluginError(
        f"uv 拉取包元数据失败: {spec}",
        payload={"package": name, "version": version, "stderr": last_err},
    )
