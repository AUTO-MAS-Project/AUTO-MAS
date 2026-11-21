"""项目对 maafw 的版本需求：自带原生库的实测版本优先于 ``requirements.txt`` 的声明。

运行池 venv 的 binding、agent 隔离 venv 的钉版、agent 运行期 pip 约束都按这里的解析口径，
两侧因此不会岔开。只读项目目录，不联网。
"""

from __future__ import annotations

import logging
from pathlib import Path

from .project_runtime import probe_bundled_maafw_version
from .requirements_file import (
    RequirementsFileError,
    read_requirements_file,
    scan_top_level_requirements,
)
from .versions import (
    exact_version_of,
    normalize_maafw_requirement,
    requirement_distribution_name,
)

logger = logging.getLogger("automas.maafw.native.requirement")


def bundled_project_maafw_requirement(project_path: Path) -> str | None:
    """按项目自带原生库的版本钉 Python binding。

    MaaFW 的 py binding 与原生库是绑定关系，跨 minor 混用不报错但行为可能不同。
    我们加载的就是项目自带的那份库（见 ``project_maafw_runtime_path``），
    所以 binding 必须跟它一致——这比 ``requirements.txt`` 的声明更可靠。

    对 MaaFramework 官方目录里 46 个 Windows 发行包做过远程勘察，结论：

    - 涉及 10 个不同的 FW 版本（4.5.3 到 5.13.0-beta.5），**PyPI 上全都有**
    - 20 个包没有 requirements.txt（agent 是 Go/C++ 或纯 Pipeline 的项目）
    - 4 个写的是无版本约束的 ``maafw`` / ``MaaFw``
    - **3 个的声明与实际发行的库对不上**：MAAAE 声明 5.3.0 实际 5.6.0、
      MaaNTE 声明 v5.10.4 实际 5.10.5、MaaADr 声明 5.12.2 实际 5.12.3

    从库二进制里读出的版本可直接对上 PyPI 的包：抽查 4.5.3 / 5.6.0 / 5.10.2 /
    5.12.2 四个版本，项目自带的库与对应 wheel 里的**逐字节相同**；本机另验过
    5.13.0b2 与 5.13.0b5 亦然。
    """

    version = probe_bundled_maafw_version(project_path)
    return f"maafw=={version}" if version else None


def declared_project_maafw_requirement(project_path: Path) -> str | None:
    matches = [
        requirement
        for requirement in load_project_requirements(project_path)
        if requirement_distribution_name(requirement) == "maafw"
    ]
    if len(matches) > 1:
        raise RuntimeError("项目 requirements.txt 声明了多个 MaaFW runtime requirement")
    return matches[0] if matches else None


def resolve_project_maafw_requirement(
    project_path: Path, *, runner_maafw_version: str | None = None
) -> str | None:
    """普通项目（非 Managed）会用到的 MaaFW requirement。

    与借运行环境（``agent_env.runtime_lease``）内的解析顺序一致：项目自带原生库的实测
    版本优先于 requirements.txt 的声明（实测 46 个发行包里有 3 个声明是陈旧的）。

    供运行前自检复用——它只需要知道「这个项目会用哪个 runtime」，不需要真的去
    准备环境，因此不联网、不建 venv。

    ``runner_maafw_version``：runner 这次实际用的 binding 版本（调用方已经备好 runner 环境）。
    项目没自带原生库、只声明了范围（源码仓的 ``MaaFw>=5.12.0``）或什么都没声明时，runner 按
    D14 把它解析成某个确切版本（本地记住的 / 本地满足的最高 / 索引最高），agent 这边照抄范围
    让 pip 自己挑，两边就可能落在协议不同的两个版本上（5.13 起协议 7 → 8）。给了就钉成它；
    已经是确切版本（自带原生库、声明写死）的不受影响。
    """

    project = Path(project_path)
    requirement = bundled_project_maafw_requirement(
        project
    ) or declared_project_maafw_requirement(project)
    if requirement is not None:
        requirement = normalize_maafw_requirement(requirement, allow_unconstrained=True)
    runner_version = str(runner_maafw_version or "").strip().lstrip("vV")
    if runner_version and (
        requirement is None or exact_version_of(requirement) is None
    ):
        return f"maafw=={runner_version}"
    return requirement


def load_project_requirements(project_path: Path) -> list[str]:
    # 与 agent 隔离 venv 同一套解析（BOM、行内注释、续行、选项行），maafw 声明后面跟着
    # 「  # via ...」时也认得出来。
    # 这里只用来找 maafw 版本声明：清单展开不了（-c / -e、-r 越界或找不到）时退回只扫顶层
    # 依赖行（跳过指令），顶层写着的声明照样认得出，记一行告警，不拦运行环境准备；
    # agent 隔离 venv 真要装这份清单时仍会照常报错。
    requirements_path = project_path / "requirements.txt"
    try:
        parsed = read_requirements_file(requirements_path)
    except RequirementsFileError as exc:
        logger.warning(
            "项目 requirements.txt 展开不了，找 maafw 版本声明时只看顶层依赖行：%s", exc
        )
        return scan_top_level_requirements(requirements_path)
    return list(parsed.requirements) if parsed is not None else []


__all__ = [
    "bundled_project_maafw_requirement",
    "declared_project_maafw_requirement",
    "load_project_requirements",
    "resolve_project_maafw_requirement",
]
