"""需要本机桌面进程授权的敏感操作。"""

import os
import secrets
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def require_local_desktop(request: Request) -> None:
    """校验主进程持有的令牌，并限制客户端和目标地址为回环。"""
    token = os.environ.get("AUTO_MAS_INSTALL_TOKEN", "")
    authorization = request.headers.get("authorization", "")
    if not token or not secrets.compare_digest(
        authorization.encode(), f"Bearer {token}".encode()
    ):
        raise HTTPException(status_code=403, detail="此操作未授权，请从桌面客户端启动或重启后端")

    def is_local(host: str | None) -> bool:
        if host == "localhost":
            return True
        try:
            return ip_address(host or "").is_loopback
        except ValueError:
            return False

    origin = request.headers.get("origin")
    try:
        source = urlsplit(origin) if origin not in (None, "null") else None
        local_origin = source is None or (
            source.scheme in ("http", "https") and is_local(source.hostname)
        )
    except ValueError:
        local_origin = False
    if (
        request.client is None
        or not is_local(request.client.host)
        or not is_local(request.url.hostname)
        or not local_origin
    ):
        raise HTTPException(status_code=403, detail="此操作仅允许本机桌面客户端")
