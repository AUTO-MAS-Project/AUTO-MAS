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

"""M9A 专项：自己的账号流程，用 MFW 的积木（第 9 步起）。

M9A 托管由 ``manager.M9AManager``（脚本级）与 ``account_run.M9AAccountRun``（账号级）运行，配置一律经
``config_view`` 读写；保存账号与配置恢复时的受管任务整理在 ``config_hooks``（配置回调与恢复池）。
登录、游戏更新、首任务时限、重试剔除这些 M9A 自己的规矩是流程里的普通代码，规则常量与判据在
``rules.py``、排队列与保存前整理在 ``arrange.py``、登录的两种结局在 ``startup.py``；``login.py``（B 服登录）与
``game_update.py``（官服客户端版本检查与安装）由流程按需导入；``migration.py`` 是旧版 M9A 专项配置的一次性迁移。
项目更新、内嵌副本、worker 运行、通知正文等都调 ``app/task/MaaFW/blocks/``、``seams/`` 下吃普通数据的叶子。

预览的规则表与导入 / 克隆拒收由 ``registration.py`` 登记的托管属主给出（``rules.M9A_PLAN_RULES``、
``rules.is_m9a_project``）。MFW 的风味机制第 11 步已删，M9A 不再有经 MFW 管理器运行的回退路径。

保持本包不在导入期拉起任何重模块：``registration.py`` 在函数里现导入流程与配置回调。
"""
