#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 端点背后的业务：``app/api/scripts.py`` 里的 ``/maafw/*`` 端点只做
取参数 → 调这里的一个函数 → ``XxxOut(**reply.out_fields())``。

- ``common``：解析 MFW 脚本、按脚本解析有效项目根、同组候选、``MaaFWApiReply``。
- ``embedded``：内嵌副本的状态 / 导入 / 克隆 / 候选来源，导入后的换类型与同组同步。
- ``interface``：interface 预览、游戏包名推断、项目内图片资源。
- ``update``：手动检查 / 应用项目更新。
- ``agent_env``：预备运行环境。
- ``shell_instances``：外壳（MFAAvalonia / MXU）配置实例的列出与导入成用户。

依赖方向只能是 ``app.api`` → 这里，不得反向导入 ``app.api``；worker 子进程的导入闭包
也不得拉进这个包（见 ``app/task/MaaFW/AGENTS.md``）。这里不 re-export，调用方按模块导入。
"""
