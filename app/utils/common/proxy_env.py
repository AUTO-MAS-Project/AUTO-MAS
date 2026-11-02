#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""子进程代理环境：不修改宿主环境，不把认证信息放进命令行。"""

import os

import httpx


def proxy_environment(proxy: httpx.Proxy | None) -> dict[str, str] | None:
    """显式代理优先于继承值；未配置时保留原有环境继承行为。

    返回值可能包含代理密码，只供子进程 env 使用，不得记录或持久化。
    """
    if proxy is None:
        return None
    url = proxy.url
    if proxy.auth is not None:
        username, password = proxy.auth
        url = url.copy_with(username=username, password=password)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    }
    environment.update(http_proxy=str(url), https_proxy=str(url), no_proxy="")
    return environment
