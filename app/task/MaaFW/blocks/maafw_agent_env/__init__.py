#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MFW agent 环境积木：项目 agent 的 Python 环境与 MaaFW 运行池。

``core/`` 是 worker 子进程与探针也会导入的部分（不许导入宿主模块），``host/`` 是宿主侧接缝。
worker 导入 ``core`` 时会先执行本文件，所以这里不导入任何东西。
"""
