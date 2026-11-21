"""agent 起动时 maafw 的 pip 约束：钉 agent 依赖清单里的 maafw、拼运行期约束文件与环境变量。

不属于原生库「识别」，是 agent 环境的事；版本来源一律取原生库识别库
（``native.requirement.resolve_project_maafw_requirement``）。worker 进程里的 runner 也直接用。
"""

from __future__ import annotations

import hashlib
import os
import tomllib
import uuid
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import InvalidWheelFilename, parse_wheel_filename
from packaging.version import InvalidVersion

from ..native.offline_dependencies import offline_dependency_files
from ..native.project_runtime import probe_bundled_maafw_version
from ..native.requirement import (
    load_project_requirements,
    resolve_project_maafw_requirement,
)
from ..native.versions import exact_version_of, requirement_distribution_name


def pin_agent_maafw_requirement(
    project_path: Path,
    packages: Sequence[str],
    *,
    runner_maafw_version: str | None = None,
) -> list[str]:
    """把 agent 依赖清单里的 maafw 钉成与 runner 加载的原生库同一个版本。

    MaaFW 的 AgentServer（跑在 agent 那一侧）与 AgentClient（跑在 runner 这一侧）
    之间有协议版本号 ``kProtocolVersion``，跨版本会直接拒绝握手，而在我们这边只
    表现为连不上。runner 加载的是项目自带的那份原生库（见
    ``project_maafw_runtime_path``），所以 agent venv 里的 binding 必须跟它一致。

    照抄 ``requirements.txt`` 做不到这件事：实测 46 个发行包里有 4 个写的是无版本
    约束的 ``maafw`` / ``MaaFw``，pip 会拉到当时的最新版。maafw 5.13.0 于
    2026-09-07 发布并把协议号从 7 抬到 8，于是这些项目的 agent venv 一旦在那之后
    重建，就会出现 AgentClient v5.12.3 对 AgentServer v5.13.0，每次运行都连不上。

    解析口径与运行池 venv 完全一致（``resolve_project_maafw_requirement``：自带
    原生库的实测版本优先于声明），两侧因此不会再岔开。

    **只替换已有的声明，不凭空追加**：没在 requirements.txt 里声明 maafw 的项目，
    agent 多半不是 Python 的或不用 binding，给它装一个用不上的包没有意义。

    ``runner_maafw_version`` 见 :func:`resolve_project_maafw_requirement`：项目没自带原生库时
    钉成 runner 实际用的版本，而不是照抄范围。
    """

    requirement = resolve_project_maafw_requirement(
        Path(project_path), runner_maafw_version=runner_maafw_version
    )
    if requirement is None:
        return list(packages)

    pinned: list[str] = []
    replaced = False
    for package in packages:
        declaration = str(package).split(";", 1)[0].strip()
        if requirement_distribution_name(declaration) != "maafw":
            pinned.append(package)
            continue
        if replaced:
            # 同名声明只保留一条，重复的丢掉；pip 拿到两条互斥的约束会直接失败。
            continue
        pinned.append(requirement)
        replaced = True
    return pinned


#: 宿主经 worker 的环境告诉 worker 把 agent 运行期 pip 约束文件写在哪（AUTO-MAS 自己的
#: ``data/maafw_agent_constraints``）。没设（本地直接跑 runner、测试）就不注入。
AGENT_PIP_CONSTRAINT_DIR_ENV = "AUTO_MAS_MAAFW_AGENT_CONSTRAINT_DIR"
#: 注入给 agent 子进程的约束变量：pip 认 ``PIP_CONSTRAINT``，``uv pip`` 认 ``UV_CONSTRAINT``。
AGENT_PIP_CONSTRAINT_ENV_KEYS: tuple[str, ...] = ("PIP_CONSTRAINT", "UV_CONSTRAINT")


@dataclass(frozen=True)
class AgentMaaFWPipConstraint:
    """agent 运行期 pip 约束的判定结果。``version`` 为 None 时不注入，``reason`` 说明为什么。"""

    version: str | None
    reason: str


def _project_declared_maafw(project: Path) -> list[tuple[str, str]]:
    """项目自己声明 / 自带的 maafw：``[(来源, requirement 文本), ...]``。

    三处都是 agent 首次启动自己装依赖时 pip 的输入：``requirements.txt``（与运行池同一套解析，
    ``load_project_requirements``）、``pyproject.toml`` 的 ``[project].dependencies``（MaaStarResonance
    ``pip install <项目根>``）、离线依赖目录里的 ``maafw-*.whl``（与准备运行环境同一套判据，
    ``offline_dependency_files``；带着确切版本的 wheel 等于自己钉了版本）。
    """

    declared: list[tuple[str, str]] = [
        ("requirements.txt", requirement)
        for requirement in load_project_requirements(project)
        if requirement_distribution_name(requirement) == "maafw"
    ]
    pyproject = project / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            # 读不了就当它声明了什么都可能：调用方按「项目自己管」处理，不注入。
            declared.append(("pyproject.toml", f"<无法解析: {exc}>"))
        else:
            project_table = data.get("project")
            dependencies = (
                project_table.get("dependencies")
                if isinstance(project_table, dict)
                else None
            )
            if isinstance(dependencies, list):
                declared.extend(
                    ("pyproject.toml", str(item))
                    for item in dependencies
                    if requirement_distribution_name(str(item)) == "maafw"
                )
    for relative in offline_dependency_files(project):
        name = relative.rsplit("/", 1)[-1]
        if not name.casefold().endswith(".whl"):
            continue
        try:
            dist, version, _build, _tags = parse_wheel_filename(name)
        except (InvalidWheelFilename, InvalidVersion):
            continue
        if dist == "maafw":
            declared.append((relative, f"maafw=={version}"))
    return declared


def agent_maafw_pip_constraint(
    project_path: Path, *, runner_maafw_version: str | None = None
) -> AgentMaaFWPipConstraint:
    """agent 子进程运行期自己跑 pip 时，maafw 该被约束在哪个版本。

    准备运行环境时已经把 agent 的 maafw 钉成与 runner 同一版本（``pin_agent_maafw_requirement``
    与自带解释器的钉回），但项目的部署脚本会在 agent 启动后自己 ``pip install --upgrade``
    （MAA_bbb：``python -m pip install --upgrade -i <镜像> MaaFw``，requirements.txt 里是无版本的
    ``MaaFw``），升到 PyPI 最新：runner 那侧的原生库与 agent 里新的 ``maa`` 包混用，自定义动作
    静默失败。约束文件让 pip 在这种升级里停在钉住的版本。

    版本与准备运行环境同一个来源（``resolve_project_maafw_requirement``：自带原生库的实测版本 →
    runner 实际加载的 binding 版本）。**项目自己钉了 maafw 就不注入**（M9A requirements.txt
    ``maafw==5.12.3``、MaaStarResonance pyproject ``maafw==5.12.1`` + 离线 wheel）：项目的自装命令
    里带着它自己的确切版本，再叠一条不同版本的约束 pip 直接 ResolutionImpossible、自装失败。
    声明的是范围、而钉住的版本不在范围里也不注入，理由相同。
    """

    project = Path(project_path)
    requirement = resolve_project_maafw_requirement(
        project, runner_maafw_version=runner_maafw_version
    )
    version = exact_version_of(requirement) if requirement else None
    if version is None:
        return AgentMaaFWPipConstraint(
            None,
            f"定不出 agent 该用的确切 maafw 版本（{requirement or '项目未声明且 runner 版本未知'}）",
        )
    for source, declared in _project_declared_maafw(project):
        label = f"{source}: {declared}"
        try:
            parsed = Requirement(declared.split(";", 1)[0].strip())
        except InvalidRequirement:
            return AgentMaaFWPipConstraint(
                None, f"项目的 maafw 声明读不懂，按项目自己管处理（{label}）"
            )
        if parsed.url or exact_version_of(str(parsed)) is not None:
            return AgentMaaFWPipConstraint(None, f"项目自己钉了 maafw 版本（{label}）")
        if parsed.specifier and not parsed.specifier.contains(
            version, prereleases=True
        ):
            return AgentMaaFWPipConstraint(
                None,
                f"项目声明的 maafw 范围不含 {version}，注入约束会让项目自装失败（{label}）",
            )
    if probe_bundled_maafw_version(project):
        source = "项目自带原生库的版本"
    else:
        source = "runner 实际加载的版本"
    return AgentMaaFWPipConstraint(version, source)


def agent_pip_constraint_file(directory: Path, project_path: Path) -> Path:
    """某个项目的约束文件路径：按项目路径哈希命名（与隔离 venv 同一种键），一个项目一份。"""

    key = str(Path(project_path).resolve())
    if os.name == "nt":
        key = key.lower()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return Path(directory) / f"maafw_agent_{digest}.txt"


def write_agent_pip_constraint(
    directory: Path, project_path: Path, version: str
) -> Path:
    """写（或复用）约束文件，返回路径。内容只用 ASCII：pip 读约束文件时没有 BOM 就按本机代码页
    解码，中文 Windows 上 UTF-8 的中文注释会读坏。"""

    path = agent_pip_constraint_file(directory, project_path)
    content = (
        "# Written by AUTO-MAS for the MaaFW agent of this project: keeps maafw on the\n"
        "# version the runner loaded, so the agent's own pip --upgrade cannot move it.\n"
        f"maafw=={version}\n"
    )
    try:
        if path.read_text(encoding="ascii") == content:
            return path
    except (OSError, UnicodeDecodeError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_text(content, encoding="ascii")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)
    return path


def apply_agent_pip_constraint(
    env: MutableMapping[str, str],
    constraint_file: Path,
) -> list[str]:
    """把约束文件挂到 ``env`` 的 ``PIP_CONSTRAINT`` / ``UV_CONSTRAINT`` 上，返回设了的变量名。

    值写成 ``file:`` URI：pip 与 uv 都按空格把这两个变量拆成多个文件，AUTO-MAS 装在带空格的
    目录里时裸路径会被拆断、项目的 pip 直接报找不到文件；URI 里空格与中文都是百分号编码，
    两者都能读（本机 pip 25.0.1 / uv 0.11.26 实测）。环境里已有值（用户自己设的）就追加在后面，
    pip 会同时遵守。PI v2 的 agent 声明没有 env 字段（``piEnv`` 只有 ``PI_*`` 键），项目没有
    渠道经 interface 自设这两个变量，所以这里不做「项目自设就跳过」的判断。
    """

    uri = Path(constraint_file).resolve().as_uri()
    applied: list[str] = []
    for key in AGENT_PIP_CONSTRAINT_ENV_KEYS:
        existing = str(env.get(key) or "").strip()
        if not existing:
            env[key] = uri
        elif uri not in existing.split():
            env[key] = f"{existing} {uri}"
        # 已经挂过就原样保留，别把前面用户自己的约束冲掉
        applied.append(key)
    return applied


__all__ = [
    "AGENT_PIP_CONSTRAINT_DIR_ENV",
    "AGENT_PIP_CONSTRAINT_ENV_KEYS",
    "AgentMaaFWPipConstraint",
    "agent_maafw_pip_constraint",
    "agent_pip_constraint_file",
    "apply_agent_pip_constraint",
    "pin_agent_maafw_requirement",
    "write_agent_pip_constraint",
]
