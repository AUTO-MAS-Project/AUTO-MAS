#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   第三方许可与来源声明：本包按下列项目公开源码所描述的流程与协议用 Python 重新实现，
#   命名分层与部分类型取自它们，代码与文档中不含其源文件副本。两者均为 MIT 许可；
#   按该许可要求保留版权声明与许可原文如下，全文另见本目录的 LICENSE.Collapse.md。
#
#   - Collapse Launcher  https://github.com/CollapseLauncher/Collapse
#     依据版本 dc47259171794596331dffcf90db85a6ac0415ac（main，2026-09-20）
#     Copyright (c) neon-nyan
#   - Hi3Helper.Sophon   https://github.com/CollapseLauncher/Hi3Helper.Sophon
#     依据版本 9189e990e2d8ef6a9ee5b3dfd77b41e1874f9cac（Collapse 的子模块）
#     Copyright (c) 2024-2025 Collapse Launcher
#
#   MIT License
#
#   Permission is hereby granted, free of charge, to any person obtaining a copy
#   of this software and associated documentation files (the "Software"), to deal
#   in the Software without restriction, including without limitation the rights
#   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the Software is
#   furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in all
#   copies or substantial portions of the Software.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#   SOFTWARE.

"""米哈游客户端更新引擎：检查更新 → 下载 → 安装，全程不依赖官方启动器界面。

按职责分成这些模块，自下而上：

- :mod:`~app.services.gi_updater.common`     与游戏无关的基础件（中止与路径异常、日志、ini、进度）
- :mod:`~app.services.gi_updater.presets`    每款游戏每个区服的预设（三元组、端点与 Sophon 目录）
- :mod:`~app.services.gi_updater.api`        HYP Connect 与 Sophon 端点：注入异步客户端、逐处窄取值
- :mod:`~app.services.gi_updater.sophon`     Sophon 清单与差分清单的 protobuf schema 与 zstd 解压
- :mod:`~app.services.gi_updater.patch`      Sophon 差分清单解析与补丁落盘
- :mod:`~app.services.gi_updater.versioning` 版本号、本地/远程版本与安装状态机
- :mod:`~app.services.gi_updater.install`    计划编排与落盘收尾
- :mod:`~app.services.gi_updater.games`      各游戏差异化钩子与 :func:`create_updater` 装配
- :mod:`~app.services.gi_updater.pipeline`   宿主侧编排：区服判定、三道门禁、面向用户的叙述

本包全异步：HTTP 客户端由调用方建好传进来（``httpx.AsyncClient``），阻塞的文件与哈希
操作走 ``asyncio.to_thread``。除了 :mod:`~app.services.gi_updater.pipeline` 取宿主的
日志与补丁工具，其余模块不 import ``app.core`` / ``app.api``，可以脱离宿主单独导入与
自测。``pipeline`` 负责握住客户端的寿命、把结论转成调度台日志、并补上只有宿主才该管的
三道门禁；一款游戏的门面只做「钉自己的短名」这一件事。

只实现 Sophon 差分一条执行链路：官方已不下发 zip 分包，传统 zip 链路（下载分包 →
解压 → hdiff → deletefiles）无对应实现；全新安装（``SophonInstall``）与全量比较
（``SophonUpdate``）只产出计划供宿主提示，无人值守一律停手交给官方启动器。要接仍以
zip 分包为主的游戏时，需要另补一条 zip 执行链路与相应的 ``UpdateKind`` 取值。

新增一款米哈游游戏（如绝区零）只需四步，不改引擎正文：在
:mod:`~app.services.gi_updater.presets` 的 ``GameKey`` 登记短名并补
``(game, region)`` 预设三元组；在 ``games/`` 下仿
:mod:`~app.services.gi_updater.games.genshin` 写一个模块，子类覆写
``filter_assets``、安装态判定等少量钩子并在末尾 ``register(GameSpec(...))``；在
:mod:`~app.services.gi_updater.games` 追加一行导入完成登记；宿主侧仿
:mod:`app.services.genshin_updater` 加一个门面。协议层（``sophon`` / ``patch``）、
下载层与装配层零改动。
"""

from app.services.gi_updater.games import GameUpdater, create_updater
from app.services.gi_updater.install import InstallResult, UpdateKind, UpdatePlan

__all__ = [
    "GameUpdater",
    "InstallResult",
    "UpdateKind",
    "UpdatePlan",
    "create_updater",
]
