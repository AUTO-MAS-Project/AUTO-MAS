#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 的规则常量与「这是不是 MSS 项目」的判据：全包只有这一份。

三个按 entry 找的任务、重试不补跑的 entry（``MSS_SKIP_ON_RETRY``）、托管类型键、计划表的固定模式都在
这里。MSS 没有规则表（不可选、关键任务、收尾任务、不回落 default 都没有），建计划用空表。
``flavor.py`` 与 ``arrange.py`` 都从这里取，之后 MSS 自己的流程也从这里取。

只依赖标准库与解析一侧的 interface 模型。
"""

from __future__ import annotations

from typing import Any

from app.task.MaaFW.tools.core.interface.models import MaaFWInterface

TYPE_KEY = "MSS"
ACTIVITY_ENTRY = "活动快速战斗_入口"
TRIBULATION_ENTRY = "战斗_入口"
CLIMB_ENTRY = "星塔_入口_agent"

PLAN_MODE_FIXED = "Fixed"

# 本次运行已成功的日常、挑战不再补跑。登录不列：重试重新启动游戏后仍要登录。
# 逐项声明已确认的公开 entry；上游新增任务默认保留重跑行为。
# 灾变防线保留在这里：它是「一期只能打一次」的常驻活动，成功后再派一遍会重新走
# 导航和走位，而这条声明只依赖引擎给的 completedTasks，与谁负责编排无关。
MSS_SKIP_ON_RETRY: frozenset[str] = frozenset(
    {
        ACTIVITY_ENTRY,
        TRIBULATION_ENTRY,
        CLIMB_ENTRY,
        "灾变防线_入口",
        "活动挑战_入口",
        "好友_入口",
        "基金_入口",
        "邀约_入口",
        "邮箱_入口",
        "猎影合围_入口",
        "真格挑战_入口",
        "委托_入口",
        "采购_入口",
        "心链_入口",
        "任务_入口",
    }
)

## 项目唯一标识符前缀：官方版是 MaaStellaSora，衍生版在其后加后缀（个人版 MaaStellaSora-Personal）。
## github 仓库名按同一口径认。
_MSS_PROJECT_NAME = "maastellasora"


def github_repo_name(github: str) -> str:
    """``github`` 里的仓库名；给不出 ``owner/repo`` 这种两段路径时返回空串。

    认这些写法：``https://github.com/owner/repo``、``https://github.com/owner/repo.git``、
    ``git@github.com:owner/repo.git``、``owner/repo``。
    只给一段的（如 ``https://github.com/MaaStellaSora`` 这种组织主页）返回空串——
    它不是一个仓库，按仓库名认领会把整个组织名下的项目都算进来。
    """

    cleaned = github.strip()
    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    cleaned = cleaned.replace(":", "/")
    cleaned = cleaned.strip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    parts = [part for part in cleaned.split("/") if part]
    if parts and ("." in parts[0] or "@" in parts[0]):
        ## 首段是主机名（github.com / git@github.com），去掉后剩下的才是路径
        parts = parts[1:]
    if len(parts) < 2:
        return ""
    return parts[-1]


def _is_mss_project_key(value: str) -> bool:
    """项目标识符是否属于 MSS：等于 ``MaaStellaSora``，或以 ``MaaStellaSora-`` 开头。

    后缀必须是连字符分隔的——``MaaStellaSora-Personal`` ✓、``MaaStellaSoraX`` ✗，
    免得把碰巧同前缀的无关项目认成衍生版。``github`` 与 ``name`` 走同一口径。
    """

    normalized = value.strip().casefold()
    return normalized == _MSS_PROJECT_NAME or normalized.startswith(
        f"{_MSS_PROJECT_NAME}-"
    )


def is_mss_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """官方版与其衍生版（个人版）都认领，三条判据任一命中即可：

    - ``mirrorchyan_rid == SSAH``：官方版在 MirrorChyan 的分发标识；
    - ``github`` 仓库名（``owner/repo`` 里的 repo）命中同一口径：官方
      ``MaaStellaSora/MaaStellaSora``、个人版 ``beichen24a1/MaaStellaSora-Personal`` 都命中；
    - ``name``（PI 的项目唯一标识符）命中同一口径。

    后两条共用 ``_is_mss_project_key``：**等于 ``MaaStellaSora`` 或以 ``MaaStellaSora-`` 开头**。
    只给 ``https://github.com/MaaStellaSora`` 这种组织主页时仓库名取不到，不会认领。

    认领只决定**托管类型**（都用 ``MSSConfig`` 与同一套运行期装饰）；更新谱系仍按
    ``mirrorchyan_rid`` / ``github`` / ``name`` 各自分开，衍生版不会被官方版的更新包覆盖。
    """

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "ssah":
        return True
    if _is_mss_project_key(github_repo_name(str(github or ""))):
        return True
    return _is_mss_project_key(str(name or ""))


__all__ = [
    "ACTIVITY_ENTRY",
    "CLIMB_ENTRY",
    "MSS_SKIP_ON_RETRY",
    "PLAN_MODE_FIXED",
    "TRIBULATION_ENTRY",
    "TYPE_KEY",
    "github_repo_name",
    "is_mss_project",
]
