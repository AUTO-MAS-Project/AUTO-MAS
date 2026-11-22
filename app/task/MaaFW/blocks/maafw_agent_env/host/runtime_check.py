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

"""运行前的运行环境自检（宿主侧，agent 环境这一块）：这个项目要用的运行池 runtime 还能用吗。

三个专项的脚本级流程都在运行前检查里调（放工作线程），只吃项目路径、返回给用户看的一句话或
None，不读脚本配置。本机不是 x64 的那句提示在原生库识别库
（``tools/core/native/architecture.describe_unsupported_architecture``），各流程直接调它。
"""

from __future__ import annotations

from pathlib import Path


def describe_unusable_runtime(project_path: Path) -> str | None:
    """运行前自检：这个项目要用的运行池 runtime 还能用吗？

    只在池里已经存在这个项目会用到的那份 runtime 时才探一次（一个子进程，约
    100ms——解释器本来就要起）。没建过就不拦：那份环境会在运行时按需准备，失败
    自有它自己的报错路径。

    runtime 的选法与借运行环境（``borrow_runtime_environment``）一致：同一份依赖选择器加同一个
    引导解释器。只按 MaaFW 版本去池里挑不行——旧版本用便携包 embeddable Python
    建出的坏环境和修好后新建的好环境 MaaFW 版本相同，挑错了会把能跑的任务拦下。

    拦在 ``check()`` 而不是只靠编辑页的提示：队列与定时任务不经过编辑页，
    绕不过 check()；而且这里拦下来时模拟器和游戏都还没启动。
    """

    # 运行池会拉起 uv 与安装器，只在真要用时导入，别让每次 import 都付这份成本。
    from app.task.MaaFW.blocks.maafw_agent_env.core.agent_env.runtime_lease import (
        describe_runner_runtime_selection,
    )
    from app.task.MaaFW.blocks.maafw_agent_env.core.runtime_pool import (
        MaaFWRuntimePoolError,
        MaaFWRuntimePoolService,
    )
    from app.task.MaaFW.blocks.maafw_agent_env.core.runtime_pool.binding import (
        verify_binding,
        verify_native,
    )

    try:
        service = MaaFWRuntimePoolService()
        # 与 prepare 同一套推导；托管解释器还没装时返回 None，runtime 也就不可能存在。
        selection = describe_runner_runtime_selection(project_path, service.pool)
        if selection is None:
            return None
    except Exception:  # noqa: BLE001 - 自检失败不该反过来挡住运行
        return None

    try:
        # 找到 base 后 get() 会真的起一次解释器核对 ABI，起不来就是坏了。
        runtime = service.pool.get(selection.runtime_id)
    except MaaFWRuntimePoolError as exc:  # 原文就是给用户看的
        return f"MFW 运行环境不可用：{exc}"
    except Exception:  # noqa: BLE001
        return None
    if runtime is None or selection.binding_version is None:
        # base 没建过 / binding 版本还没定：运行时按需准备，失败自有它的报错路径
        return None
    try:
        # binding 目录存在但清单校验不过（被删了一半、文件被改）→ 拦下来说清楚；
        # 压根没有则同样交给运行时准备。
        binding_dir = (
            service.pool.root / "bindings" / f"maafw-{selection.binding_version}"
        )
        if (
            binding_dir.is_dir()
            and verify_binding(service.pool.root, selection.binding_version) is None
        ):
            return (
                f"MFW 运行环境不可用：maafw {selection.binding_version} 的 binding 目录"
                f"校验不通过（{binding_dir}），请重新准备运行环境"
            )
        native_dir = service.pool.root / "native" / f"maafw-{selection.binding_version}"
        if (
            selection.native_needed
            and native_dir.is_dir()
            and verify_native(service.pool.root, selection.binding_version) is None
        ):
            return (
                f"MFW 运行环境不可用：maafw {selection.binding_version} 的官方原生库目录"
                f"校验不通过（{native_dir}），请重新准备运行环境"
            )
    except Exception:  # noqa: BLE001
        return None
    return None


__all__ = ["describe_unusable_runtime"]
