#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""MSS（MaaStellaSora / 星塔旅人）专项：自己的账号流程，用 MFW 的积木。

第 10 步起 MSS 托管跑本包自己的两层流程（``manager.MSSManager`` → ``account_run.MSSAccountRun``，
配置只经 ``config_view`` 读写），不经 MFW 管理器；项目更新、运行池、agent 环境、worker
运行、判定、记账、通知正文等仍调 ``app/task/MaaFW/tools/`` 下吃普通数据的叶子。规则常量与项目判据在
``rules.py``，排队列的前后两段（活动探测前、后）在 ``arrange.py``。

导入 / 克隆拒收由 ``registration.py`` 登记的托管属主给出（``rules.is_mss_project``），MSS 的规则表为空。
MFW 的风味机制第 11 步已删，MSS 不再有经 MFW 管理器运行的回退路径。
保持本包不在导入期拉起任何重模块：``registration.py`` 在函数里现导入流程模块。
"""
