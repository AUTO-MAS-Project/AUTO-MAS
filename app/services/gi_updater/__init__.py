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

"""原神客户端更新引擎：检查更新 → 下载 → 安装，全程不依赖官方启动器界面。

分四层，自下而上：

- :mod:`~app.services.gi_updater.common`    与游戏无关的基础件（版本号、ini、路径、进度）
- :mod:`~app.services.gi_updater.api`       预设、启动器元数据接口与阻塞式 HTTP 客户端
- :mod:`~app.services.gi_updater.versioning` 本地/远程版本、安装状态机与包清单决策
- :mod:`~app.services.gi_updater.download`  Sophon 清单解析、zstd/protobuf 解码与分块下载
- :mod:`~app.services.gi_updater.install`   计划编排与落盘收尾
- :mod:`~app.services.gi_updater.games`     原神差异化钩子与 :func:`create_updater` 装配

本包**全同步**（urllib + 线程 + 阻塞文件 IO），不 import ``app.core``/``app.api``，
可以脱离宿主单独导入与自测；异步边界与宿主接线在
:mod:`app.services.genshin_updater` 门面里做。

只实现 Sophon 一条链路：原神自 5.6 起官方不再下发 zip 分包，两个区服预设都置
``is_force_redirect_to_sophon``，传统 zip 链路（下载分包 → 解压 → hdiff →
deletefiles）对本包永远不可达，故未收录。要接不支持强制 Sophon 的游戏时，
需要补回 ``install/zip_flow.py``、``download/http.py`` 的多会话分片下载器，
以及 ``UpdateKind`` 的 zip 取值与 ``build_plan`` 的链路判定。
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
