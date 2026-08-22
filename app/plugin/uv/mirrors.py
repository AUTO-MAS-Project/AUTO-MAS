"""PyPI simple 镜像：候选列表、成功源置顶并写入 ``Config.setting.uv``。"""

from __future__ import annotations

# ── PyPI simple 镜像源列表（顺序即优先级），直接存储完整 URL ──
_MIRRORS: list[str] = [
    "https://mirrors.aliyun.com/pypi/simple/",  # aliyun
    "https://pypi.tuna.tsinghua.edu.cn/simple/",  # tuna
    "https://pypi.mirrors.ustc.edu.cn/simple/",  # ustc
    "https://pypi.org/simple/",  # pypi
]


def candidates() -> list[str]:
    """当前候选 ``--index-url``；已验证成功的镜像置顶且无重复。"""
    from app.core.config import Config  # noqa: F811

    preferred = Config.setting.uv.preferred_mirror or _MIRRORS[0]

    # dict.fromkeys 去重并保持插入顺序（Python 3.7+）
    return list(dict.fromkeys([preferred, *_MIRRORS]))


async def mark_ok(mirror_url: str) -> None:
    """某镜像成功后置顶，并持久化完整 URL 到 ``Config.setting.uv.preferred_mirror``。"""
    needle = mirror_url.rstrip("/")

    # 归一化比较，避免尾部斜杠差异导致误判
    if not any(url.rstrip("/") == needle for url in _MIRRORS):
        return

    from app.core.config import Config  # noqa: F811

    current = (Config.setting.uv.preferred_mirror or _MIRRORS[0]).rstrip("/")
    if current == needle:
        return

    Config.setting.uv.preferred_mirror = mirror_url
    await Config.setting.commit()
