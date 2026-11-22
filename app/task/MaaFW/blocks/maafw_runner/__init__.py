#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MFW 运行积木：worker 子进程、运行计划下发与运行结果。

worker 以 ``python -m <本积木>.core.runner.worker`` 起在运行池的隔离 venv 里，``python -m`` 会先执行
本文件与 ``core/__init__.py``，所以这两处不导入任何东西。``host/`` 是宿主侧接缝。
"""
