#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


import os


def is_supervised() -> bool:
    """识别当前进程是否处于外部监督器（AUTO-MAS-Runtime）托管之下。

    Runtime 用 Windows Job Object 托管后端进程树，拉起时注入
    AUTO_MAS_SUPERVISED=1，并经 AUTO_MAS_SUPERVISED_PORT 注入监听端口据此做
    健康检查，关闭时依赖 /api/core/close 真正生效。判据按其契约要求精确匹配
    字符串 "1"，不做 true/yes 等宽松解析。

    main.py 与 app/api/core.py 都据此判断是否遵守受监督约定
    （不自行提权、端口由运行时注入、关闭请求真实生效），因此放在两者都能直接
    依赖的 app.utils 里，避免互相导入。
    """

    return os.getenv("AUTO_MAS_SUPERVISED") == "1"


def is_backend_dev_mode() -> bool:
    """判断后端是否处于开发模式（后端由开发者独立管理，前端不得强杀）。

    dev 分支的 AUTO_MAS_DEV 标记“由前端拉起”（跳过自行提权），生产环境同样为 1，
    不能作为开发模式依据；以 main.py 启动时归一化的 AUTO_MAS_ENV 为准。

    受 AUTO-MAS-Runtime 监督时优先级高于 AUTO_MAS_DEV 与 AUTO_MAS_ENV，恒为
    False：监督器依赖 /api/core/close 真正退出进程，若判定为开发模式，
    _shutdown_backend() 只做轻量清理、不设 should_exit，关闭请求就会永远
    不生效，5 秒后被监督器硬杀。
    """

    if is_supervised():
        return False

    raw = str(os.getenv("AUTO_MAS_ENV", "")).strip().lower()
    return raw in {"dev", "development"}
