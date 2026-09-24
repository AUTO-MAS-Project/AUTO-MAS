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

"""M9A：MaaFW 引擎的特调类型，不是独立专项。

这里只有三样东西：``flavor.py``（运行前的队列装饰 + "是不是 M9A 项目"的判据 + 游戏更新
钩子）、``game_update.py``（官服客户端版本检查与安装，由钩子按需导入）与
``migration.py``（旧版 M9A 专项配置的一次性迁移）。运行、更新、内嵌副本、通知全走
``app/task/MaaFW/``。保持本包不在导入期拉起任何重模块：``app.models.config`` 在类属性里
只记了 ``"app.task.M9A.flavor:FLAVOR"`` 这个字符串，引擎按需导入。
"""
