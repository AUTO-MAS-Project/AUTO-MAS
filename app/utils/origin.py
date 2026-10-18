#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""请求来源（Origin）白名单：仅放行本机界面与回环开发服务器。

后端只监听回环，浏览器同源策略之外仍有两类入口：本机 Electron 界面
（打包后从 file:// 加载，跨源请求 Origin 为 "null"）与开发态 Vite 页面
（回环地址）。其余网页来源一律不认，避免任意网站借用户浏览器操作本机后端。
"""

from __future__ import annotations

import re

#: 非回环字面量来源：Electron 打包页 file:// 在跨源请求里的 Origin 值。
ALLOWED_LITERAL_ORIGINS = ("null", "file://")

#: 回环开发服务器来源（http/https + localhost/127.0.0.1/[::1]，端口任意）。
ALLOWED_ORIGIN_REGEX = r"^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"

_LOOPBACK_ORIGIN_PATTERN = re.compile(ALLOWED_ORIGIN_REGEX)


def is_allowed_origin(origin: str | None) -> bool:
    """判断 Origin 是否来自本应用自身（file:// 或回环开发服务器）。

    没有 Origin 头的是非浏览器客户端（Electron 主进程、Runtime 监督器、测试），
    它们不受同源策略约束，来源由「后端仅监听回环」限制，这里放行。
    """

    if origin is None:
        return True
    return origin in ALLOWED_LITERAL_ORIGINS or bool(
        _LOOPBACK_ORIGIN_PATTERN.match(origin)
    )
