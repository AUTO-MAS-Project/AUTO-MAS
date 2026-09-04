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
