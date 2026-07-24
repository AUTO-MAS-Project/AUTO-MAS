from __future__ import annotations

from urllib.parse import urlsplit


_RESERVED_ARGUMENT_PREFIXES = (
    "--profile-directory",
    "--remote-debugging-address",
    "--remote-debugging-port",
    "--user-data-dir",
)


def validate_browser_url(value: str) -> str:
    url = str(value or "").strip()
    if url == "about:blank":
        return url
    if len(url) > 4096:
        raise ValueError("浏览器 URL 过长")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("浏览器 URL 仅支持 http、https 或 about:blank")
    if parsed.username or parsed.password:
        raise ValueError("浏览器 URL 不允许包含用户名或密码")
    return url


def validate_launch_arguments(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        argument = str(raw or "").strip()
        if not argument:
            continue
        lowered = argument.lower()
        if any(lowered.startswith(prefix) for prefix in _RESERVED_ARGUMENT_PREFIXES):
            raise ValueError(f"浏览器启动参数由插件托管，不允许覆盖: {argument.split('=', 1)[0]}")
        result.append(argument)
    return result
