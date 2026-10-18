"""MFW 日志脱敏：用户主目录换成 ``<HOME>``。

app.log 会随日志包、问题包、Runtime 抓下的后端输出被发出去，``C:\\Users\\<Windows 用户名>``
不该原样留在里面。全局的 ``app.utils.security.sanitize_log_message`` 只管参数名式的令牌与
推送地址，不管用户目录；前端导出时（``issueReportCore.ts`` 的 ``sanitizeText``）才把
``os.homedir()`` 换成 ``<HOME>``，这里与它同一个记号。

放在 ``tools/core`` 而不是 ``app/utils``：worker 子进程（runner 子树）与 agent 环境准备也要用，
它们的导入闭包里只能有 ``app.task.MaaFW.tools.core`` 之下的模块（见 MaaFW/AGENTS.md），宿主侧
的 MFW 代码照样能引。只依赖标准库。
"""

from __future__ import annotations

import functools
import os
import re

HOME_TOKEN = "<HOME>"


@functools.lru_cache(maxsize=8)
def _home_pattern(homes: tuple[str, ...]) -> re.Pattern[str] | None:
    alternatives: list[str] = []
    for home in homes:
        text = str(home or "").strip()
        parts = [part for part in re.split(r"[\\/]+", text) if part]
        if len(parts) < 2:
            # 根目录、只有盘符这种不遮：会把所有路径都换掉。
            continue
        # 正斜杠、反斜杠、repr 里的双反斜杠都算分隔符。
        body = r"[\\/]+".join(re.escape(part) for part in parts)
        if text[:1] in {"/", "\\"}:
            body = r"[\\/]+" + body
        alternatives.append(body)
    if not alternatives:
        return None
    alternatives.sort(key=len, reverse=True)
    # 后面紧跟的不能还是名字的一部分（C:\Users\ab 不该盖住 C:\Users\abc）。
    return re.compile(
        rf"(?:{'|'.join(alternatives)})(?![A-Za-z0-9_.-])", flags=re.IGNORECASE
    )


def _current_homes() -> tuple[str, ...]:
    candidates = [
        os.environ.get("USERPROFILE") or "",
        os.environ.get("HOME") or "",
        os.path.expanduser("~"),
    ]
    return tuple(sorted({item for item in candidates if item and item != "~"}))


def mask_home_path(text: object) -> str:
    """把文本里的用户主目录前缀换成 ``<HOME>``（大小写不敏感，正反斜杠都认）。"""

    value = str(text)
    pattern = _home_pattern(_current_homes())
    if pattern is None:
        return value
    return pattern.sub(HOME_TOKEN, value)


__all__ = ["HOME_TOKEN", "mask_home_path"]
