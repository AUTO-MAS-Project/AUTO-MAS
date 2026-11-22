#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MFW 项目更新积木：内嵌项目的导入、视图、版本检查与更新。

``core/`` 是更新子进程也会导入的部分（不许导入宿主模块，``app.utils`` 的两处已知例外见守卫），
``host/`` 是宿主侧接缝。这里不导入任何东西。
"""
