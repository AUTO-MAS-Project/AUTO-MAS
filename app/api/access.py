#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""本机 HTTP / WebSocket 的浏览器来源边界。"""

from starlette.datastructures import URL, Headers
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send


class LocalAccessMiddleware(CORSMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            desktop = headers.get("x-auto-mas-client") == "desktop"
            allowed = URL(scope=scope).hostname in ("127.0.0.1", "localhost", "::1")
            if origin in ("null", "file://"):
                # 仅 Electron 主进程给本应用文件页注入标记；网页预检本身不携带此头。
                allowed = allowed and desktop
            elif origin is not None:
                allowed = allowed and self.is_allowed_origin(origin)
            elif headers.get("sec-fetch-site") == "cross-site":
                allowed = allowed and desktop

            if not allowed:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse(
                        {
                            "code": 403,
                            "status": "error",
                            "message": "拒绝非本机应用访问",
                        },
                        status_code=403,
                    )(scope, receive, send)
                return
        await super().__call__(scope, receive, send)
