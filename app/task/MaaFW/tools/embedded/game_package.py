#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""从 MFW 项目里推断它操作的那个安卓游戏的包名。

**为什么要推。** 模拟器可以在启动时顺带把游戏拉起来（``DeviceBase.open`` 的
``package_name``），省掉脚本自己从冷启动等起的那一段。但包名每个项目、每个服务器都
不一样，让用户手填一遍是重复劳动——项目里其实已经写着了。

**它写在哪。** ``interface.json`` 里**没有**包名字段（MaaFramework 的 ProjectInterface
规格里就没这一项），实测两个真实项目也都没有。真正的包名在 pipeline 节点的 ``StartApp``
动作参数里，而且两种放法都存在：

- **放在 resource 的 pipeline 文件里**，按服务器分目录。M9A 九个服各自在
  ``resource/<服>/pipeline/startup.json`` 里覆盖**同一个**节点 ``Start1999``，
  由 ``interface.json`` 的 ``resource[].path`` 给出叠加顺序（国际服 EN 是
  ``base`` + ``global_jp`` + ``global_en``），后面的覆盖前面的。
- **放在 task / option 的 ``pipeline_override`` 里**。MaaEnd 的包名取决于用户选的
  ``ClientVersion`` option，根本不在 resource 目录里。

所以这里按同一套顺序叠加：先按 ``resource[].path`` 的顺序扫 pipeline，再把运行计划里
已选任务的 ``pipelineOverride`` 盖上去，最后看还剩几个互不相同的包名。还剩多个时再按
「后面的层更具体」取最后一层的（渠道服资源层常常是新增一个启动节点而不是覆盖同名节点，
Maa_bbb 就是这样），最后一层自己就有多个才算真的推不出。

**这是约定，不是契约。** ``StartApp`` 是 MaaFramework 的标准动作，但没有任何规格要求
项目必须用它启动游戏——interface 是 MXU / MFAAvalonia 这些客户端写的，我们只是读者。
所以「推不出来」是正常结果而不是错误，调用方应当回落到用户手填的包名；**推出多个互相
矛盾的包名时同样不猜**，见 :class:`PackageResolution`。
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.task.MaaFW.tools.core.automas_maafw_interface.loader import parse_json_text
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWInterface
from app.utils import get_logger

logger = get_logger("MaaFW 包名识别")

#: MaaFramework 里「启动应用」这个动作的类型名。
_START_APP_ACTION = "StartApp"

#: resource 目录下放 pipeline 的子目录名，MaaFramework 的固定约定。
_PIPELINE_DIR_NAME = "pipeline"

#: pipeline 文件的后缀。规格允许 JSON5，``parse_json_text`` 两种都认。
_PIPELINE_SUFFIXES = (".json", ".jsonc", ".json5")


@dataclass(frozen=True)
class PackageResolution:
    """一次包名推断的结果。

    ``ambiguous`` 是有意保留的一档：叠加完还剩多个不同的包名，说明这个项目的写法
    超出了上面那套模型，此时**宁可什么都不给**也不要挑一个——挑错了会去启动另一个
    游戏，比不启动更糟。
    """

    reason: Literal["resolved", "not-found", "ambiguous"] = "not-found"
    """推断走到哪一步结束的。"""

    package: str = ""
    """推出来的包名；只有 ``reason == "resolved"`` 时才非空。"""

    candidates: tuple[str, ...] = field(default_factory=tuple)
    """``ambiguous`` 时的全部候选，按字典序，给日志用。"""


def normalize_package(raw: str) -> str:
    """``包名/Activity`` → ``包名``。

    ``StartApp`` 的 ``package`` 参数两种写法都有：M9A 官服写的是
    ``com.shenlan.m.reverse1999/com.ssgame...AppStartUpActivity``，而它的国际服和
    ``StopApp`` 写的是裸包名。模拟器那边只要包名。
    """
    return (raw or "").strip().split("/", 1)[0].strip()


def collect_start_app_nodes(pipeline: Any) -> dict[str, str]:
    """从一份 pipeline（或一份 ``pipeline_override``）里取出 ``{节点名: 包名参数}``。

    两种写法都认：

    - 嵌套写法 ``{"action": {"type": "StartApp", "param": {"package": ...}}}``
      （M9A、MaaEnd、法奥斯之矛）；
    - 扁平写法 ``{"action": "StartApp", "package": ...}``（MaaYYs、Maa_bbb、MaaKes
      的任务 override）。MaaFramework 两种都接受，项目里两种都在用。

    ``StopApp`` 也带 ``package``，不能算进来。别的写法当推不出来，由用户手填兜底。
    """
    if not isinstance(pipeline, Mapping):
        return {}

    found: dict[str, str] = {}
    for node_name, node in pipeline.items():
        if not isinstance(node, Mapping):
            continue
        action = node.get("action")
        if isinstance(action, Mapping):
            if action.get("type") != _START_APP_ACTION:
                continue
            package = action.get("param", {})
            if isinstance(package, Mapping):
                package = package.get("package")
        elif action == _START_APP_ACTION:
            package = node.get("package")
        else:
            continue
        if isinstance(package, str) and package.strip():
            found[str(node_name)] = package
    return found


def _iter_pipeline_files(resource_path: Path) -> Iterator[Path]:
    """一个 resource 目录下的全部 pipeline 文件，按路径排序保证结果可复现。"""
    pipeline_dir = resource_path / _PIPELINE_DIR_NAME
    if not pipeline_dir.is_dir():
        return
    for file in sorted(pipeline_dir.rglob("*")):
        if file.is_file() and file.suffix.lower() in _PIPELINE_SUFFIXES:
            yield file


def resource_paths_for(
    root_path: Path, interface: MaaFWInterface, resource_name: str
) -> list[Path]:
    """``interface.resource[name].path`` 解析成项目内的目录列表，保持声明顺序。

    给脚本编辑页用：那里还没有运行计划，只知道用户选了哪个 resource。
    找不到该 resource 返回空列表；越界（跳出项目目录）与不存在的条目直接跳过——
    这里只是推包名，不是在校验项目。
    """

    root = Path(root_path).resolve()
    resource = next(
        (item for item in interface.resource if item.name == resource_name), None
    )
    if resource is None:
        return []
    paths: list[Path] = []
    for raw in resource.path or []:
        candidate = Path(str(raw).replace("{PROJECT_DIR}", str(root)))
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.is_dir():
            paths.append(resolved)
    return paths


def resolve_game_package(
    resource_paths: Sequence[Path],
    task_overrides: Sequence[Mapping[str, Any]] = (),
) -> PackageResolution:
    """按 resource 叠加顺序 + 已选任务的 override 推断游戏包名。

    ``resource_paths`` 必须是 ``interface.json`` 里 ``resource[].path`` 解析后的
    **顺序**列表——顺序就是覆盖顺序，传错顺序会拿到上一层的包名。

    这个函数只读文件、不抛异常：读不动或解析不了的文件跳过并记 debug，因为项目里
    混进一个坏 JSON 不该让整次代理失败。
    """
    # 节点名 → (包名, 来自第几层)。层序 = resource 声明顺序
    nodes: dict[str, tuple[str, int]] = {}
    for layer, resource_path in enumerate(resource_paths):
        for file in _iter_pipeline_files(resource_path):
            try:
                data = parse_json_text(file.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001 - 见 docstring：坏文件跳过，不中断
                logger.debug(f"跳过读不出的 pipeline 文件 {file}: {e}")
                continue
            for node_name, raw in collect_start_app_nodes(data).items():
                nodes[node_name] = (raw, layer)

    # override 最后盖：它来自用户在界面上选的 option，比 resource 里的默认值更具体。
    # 但 override 只按节点名覆盖，盖到别的节点上时两个 StartApp 会并存，那就真的
    # 无从知道任务入口走哪一个——这种情况不套下面「后面的层更具体」的规则。
    override_touched = False
    override_layer = len(resource_paths)
    for override in task_overrides:
        for node_name, raw in collect_start_app_nodes(override).items():
            nodes[node_name] = (raw, override_layer)
            override_touched = True

    by_package: dict[str, int] = {}
    for raw, node_layer in nodes.values():
        package = normalize_package(raw)
        if package:
            by_package[package] = max(by_package.get(package, -1), node_layer)

    if len(by_package) == 1:
        return PackageResolution(reason="resolved", package=next(iter(by_package)))
    if not by_package:
        return PackageResolution(reason="not-found")

    # 只在 resource 层之间多个包名时再看一层：渠道服资源层往往**新增**一个自己的启动节点
    # 而不是覆盖 base 的（Maa_bbb 的 resource_bilibili 就是这么写的），按「后面的层更具体」
    # 取最后一层里的包名；最后一层自己就有多个才算真的 ambiguous。
    if not override_touched:
        top_layer = max(by_package.values())
        top_packages = [
            pkg for pkg, node_layer in by_package.items() if node_layer == top_layer
        ]
        if len(top_packages) == 1:
            return PackageResolution(reason="resolved", package=top_packages[0])
    return PackageResolution(reason="ambiguous", candidates=tuple(sorted(by_package)))


__all__ = [
    "PackageResolution",
    "collect_start_app_nodes",
    "normalize_package",
    "resolve_game_package",
    "resource_paths_for",
]
