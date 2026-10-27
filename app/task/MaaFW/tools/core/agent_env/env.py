from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from packaging.version import InvalidVersion, Version

from ..interface.agent_entry import describe_uv_agent, is_uv_launcher
from ..log_redact import mask_home_path
from ..offline_dependencies import describe_self_install_materials
from ..runtime_pool import runtime_managed_uv_executable
from ..runtime_pool._shared import (
    mask_url_credentials,
    output_tail,
    remove_tree_best_effort,
)
from ..runtime_pool.host_environment import (
    EMBEDDED_COPIES_DIR_PARTS,
    set_project_pycache_prefix,
    strip_host_python_environment,
)
from ..runtime_pool.installer import (
    is_package_index_offline,
    resolve_package_index_candidates,
)
from ..runtime_pool.requirements_file import (
    RequirementsFileError,
    read_requirements_file,
)
from .models import MaaFWAgentCommandPlan, MaaFWAgentEnvPrepareResult
from .planner import MaaFWAgentEnvError, venv_base_python_missing, venv_python_exe
from .venv_share import (
    VENV_TRASH_MARKER,
    VenvLockTimeout,
    is_shared_venv_name,
    isolated_venv_guard,
    legacy_isolated_venv_name,
    resolve_agent_venv_root,
    shared_venv_key_inputs,
    shared_venv_name,
    venv_thread_lock,
    write_venv_ref,
)

logger = logging.getLogger("automas.maafw.agent_env.env")

AGENT_BOOTSTRAP_PACKAGE = "json-with-comments"
AGENT_ENV_MANIFEST_NAME = ".auto_mas_agent_env.json"
AGENT_COMPAT_SHIM_DIR_NAME = ".auto_mas_shims"
PIP_HEALTH_CHECK_TIMEOUT = 15
PROJECT_PYTHON_HEALTH_TIMEOUT = 15
PIP_INSTALL_TIMEOUT = 120
# pip install 本身单独给足余量：与运行池的 RUNTIME_INSTALL_TIMEOUT_SECONDS 对齐，
# 且每个镜像候选各享一次完整超时。venv 创建与 ensurepip 仍用上面那个。
PIP_INSTALL_PER_INDEX_TIMEOUT = 300
# 与 runner.DETAIL_LOG_PREFIX 同一个前缀（runner.py 会 import maa，这里不能引它）：
# worker 里宿主据此只写进 .worker.log，宿主侧的更新日志据此只写后端日志，都不上界面。
DETAIL_LOG_PREFIX = "[MaaFW 详情] "
# 完整输出进详情日志时的上限（按结尾截），挡住异常情况下的超长输出。
DETAIL_OUTPUT_LIMIT = 20000
#: Agent 程序文件不见了时给用户的处理建议。准备运行环境（声明的程序不存在）与 runner 起
#: agent 时的 WinError 2（``runner._agent_spawn_error_hint``）共用：运行期先准备环境再
#: Popen，杀软刚隔离掉 agent.exe 时用户先看到的是准备环境这一句。
AGENT_PROGRAM_MISSING_HINT = (
    "常见原因是被杀毒软件隔离或删除；请检查杀毒软件的隔离区并把项目目录加入信任，"
    "确认无误后在脚本页重新导入项目"
)
VENV_PROBE_TIMEOUT = 30
# uv 兜底可能需要下载 managed Python,给足余量
UV_VENV_TIMEOUT = 300


def prepare_agent_envs(
    project_path: str | Path,
    plans: list[MaaFWAgentCommandPlan],
    *,
    send_log: Callable[[str], None] | None = None,
    bootstrap_python: str | None = None,
    install_dependencies: bool = True,
    progress: Callable[[dict[str, object]], None] | None = None,
    runner_maafw_version: str | None = None,
    lenient_health_check: bool = False,
) -> MaaFWAgentEnvPrepareResult:
    """备好各 agent 的运行环境。

    ``runner_maafw_version``：runner 这次实际用的 maafw 版本（宿主备完 runner 环境后、worker
    从 job 的 ``PI_CLIENT_MAAFW_VERSION`` 取）。项目没自带原生库时隔离 venv 里的 maafw 钉成它
    （见 ``runner.environment.resolve_project_maafw_requirement``），两侧才不会落到协议不同的
    版本上；自带原生库的项目钉的本来就是确切版本，不受影响。

    ``lenient_health_check``：项目自带 Python 的健康检查「报错照跑」，只给运行时传（worker 起
    agent 前、宿主运行前 / 运行后的环境确认），见 :func:`_prepare_project_python_env`。缺省严格：
    更新预检、编辑页手动准备、手动更新与同组传播后的确认都不传，漏改的调用点也不会被放宽。
    放行的原因记在结果的 ``healthWarnings``。
    """

    resolved_project_path = Path(project_path).resolve()
    messages: list[str] = []
    prepared_venvs: list[str] = []
    skipped: list[str] = []
    health_warnings: list[str] = []

    def log(message: str) -> None:
        messages.append(message)
        if send_log is not None:
            send_log(message)

    for path_name in ("debug", "logs", "temp"):
        (resolved_project_path / path_name).mkdir(exist_ok=True)

    checked_python: set[str] = set()
    total_plans = len(plans)
    _report_agent_progress(
        progress,
        status="running",
        message=f"准备 {total_plans} 个 MaaFW Agent 环境",
        percent=0.0,
        completed=0,
        total=total_plans,
    )

    def report_plan_complete(index: int, plan: MaaFWAgentCommandPlan) -> None:
        _report_agent_progress(
            progress,
            status="running",
            message=f"Agent 环境准备完成: {plan.childExec}",
            percent=((index + 1) * 100.0 / total_plans if total_plans else 100.0),
            completed=index + 1,
            total=total_plans,
        )

    for index, plan in enumerate(plans):
        if is_uv_launcher(plan.childExec):
            # 导入时已经拒绝；这里兜住导入早于这条规则的老副本，别等到连接超时。
            raise MaaFWAgentEnvError(describe_uv_agent(f"Agent {plan.childExec}"))
        plan_venv_name: str | None = None
        if (plan.runtimeKind or "external") == "isolated_venv":
            # 计划里的目录是建计划时按当时能拿到的信息算的；这里按 runner 这次的确切 maafw
            # 版本定下来，并改写计划（worker 随后按它起 agent，结果里的计划也是它）。
            venv_target, plan_venv_name = _resolve_isolated_venv_target(
                plan,
                resolved_project_path,
                log,
                runner_maafw_version=runner_maafw_version,
            )
            _retarget_isolated_plan(plan, venv_target, log)
        _report_agent_progress(
            progress,
            status="running",
            message=f"正在准备 Agent: {plan.childExec}",
            percent=(index * 100.0 / total_plans if total_plans else 100.0),
            completed=index,
            total=total_plans,
        )
        python_exe = plan.command[0] if plan.command else plan.executable
        resolved_python = _safe_resolve_python(python_exe)
        if resolved_python in checked_python:
            log(f"[Python环境] 已检查过该 Python，跳过重复检查: {python_exe}")
            report_plan_complete(index, plan)
            continue

        runtime_kind = plan.runtimeKind or "external"
        log(f"[Python环境] Agent {plan.childExec} 使用 {runtime_kind}: {python_exe}")
        if plan.fallbackReason:
            # 入口按 CFA 兜底、解释器换成隔离 venv 这类回退只写在计划里，不打出来的话
            # 日志包里看不出 agent 实际跑的是哪个入口。
            log(
                mask_home_path(
                    f"[Python环境] Agent {plan.childExec} 的回退说明："
                    f"{plan.fallbackReason}"
                )
            )
        if runtime_kind == "isolated_venv":
            # 共用的 venv 可能正由另一个视图准备（本进程的另一线程，或宿主 / worker 另一个
            # 进程）：线程锁 + 锁文件串行化，等的一方看到的只会是建好的或没建的。
            try:
                with isolated_venv_guard(
                    Path(plan.isolatedVenvPath or python_exe), log=log
                ):
                    prepared_path = _prepare_isolated_venv_env(
                        plan,
                        resolved_project_path,
                        log,
                        bootstrap_python=bootstrap_python,
                        install_dependencies=install_dependencies,
                        runner_maafw_version=runner_maafw_version,
                    )
                    _record_isolated_venv_ref(
                        prepared_path, resolved_project_path, plan_venv_name, log
                    )
            except VenvLockTimeout as exc:
                raise MaaFWAgentEnvError(str(exc)) from exc
            prepared_venvs.append(str(prepared_path))
            checked_python.add(resolved_python)
            report_plan_complete(index, plan)
            continue

        if runtime_kind == "project_python":
            warning = _prepare_project_python_env(
                python_exe,
                resolved_project_path,
                log,
                lenient=lenient_health_check,
            )
            if warning:
                health_warnings.append(warning)
            checked_python.add(resolved_python)
            report_plan_complete(index, plan)
            continue

        if runtime_kind == "shared_runtime":
            if not Path(resolved_python).is_file():
                raise MaaFWAgentEnvError(
                    f"共享 MaaFW runtime Python 不存在或不可用：{python_exe}"
                )
            checked_python.add(resolved_python)
            log(f"[Python环境] 共享 MaaFW runtime Python 已就绪: {python_exe}")
            report_plan_complete(index, plan)
            continue

        if (
            runtime_kind == "external"
            and plan.executableExists is False
            and not Path(plan.executable).is_file()
        ):
            # 带路径的 child_exec 解析到项目里却没有这个文件（发行包漏带、被杀软隔离）：
            # 跳过的话这里报「已就绪」、更新预检也放行，之后每次运行都死在起 agent 那一步。
            # 只看写了路径的（exists=False）；命令名形式（exists=None）交给 PATH，照旧跳过。
            # 再 stat 一次：计划可能是之前建的，文件后来补上了就不拦。
            raise MaaFWAgentEnvError(
                "声明的 Agent 程序不存在："
                f"{_project_relative_text(str(plan.executable), resolved_project_path)}"
                f"（interface 写的是 {plan.childExec}）。{AGENT_PROGRAM_MISSING_HINT}"
            )
        skipped.append(plan.childExec)
        log(f"[Python环境] 跳过外部或非 Python 环境检测: {python_exe}")

        report_plan_complete(index, plan)

    _report_agent_progress(
        progress,
        status="ready",
        message="MaaFW Agent 环境准备完成",
        percent=100.0,
        completed=total_plans,
        total=total_plans,
    )

    return MaaFWAgentEnvPrepareResult(
        projectPath=str(resolved_project_path),
        plans=plans,
        preparedVenvs=prepared_venvs,
        skipped=skipped,
        messages=messages,
        healthWarnings=health_warnings,
    )


def build_agent_env_manifest(
    project_path: str | Path, *, runner_maafw_version: str | None = None
) -> dict[str, object]:
    """隔离 venv 的 ``.auto_mas_agent_env.json``。

    ``venvKey`` 是共用目录名（依赖清单 + maafw requirement + 宿主身份，见 ``venv_share``），
    共用的 venv 只按它与 ``requirementsHash`` 判定是否还能用；``projectPath`` /
    ``interfaceHash`` 在共用的 venv 里只记录建它的那个视图，不参与判定——否则同一项目的
    另一个视图、或依赖没变的新版本会把别人正在用的 venv 删了重建。升级前按项目路径建的
    老目录仍按这两项加 ``requirementsHash`` 判定（``_isolated_venv_mismatch``）。
    """

    resolved_project_path = Path(project_path).resolve()
    inputs = shared_venv_key_inputs(
        resolved_project_path, runner_maafw_version=runner_maafw_version
    )
    requirements = list(inputs["requirements"])
    return {
        "schemaVersion": 2,
        "projectPath": str(resolved_project_path),
        "interfaceHash": _project_interface_hash(resolved_project_path),
        "requirementsHash": _requirements_hash(requirements),
        "requirements": requirements,
        "venvKey": shared_venv_name(inputs),
        "maafwRequirement": inputs["maafw"],
        "host": inputs["host"],
    }


def write_agent_compat_shims(venv_path: str | Path) -> Path:
    shim_dir = Path(venv_path) / AGENT_COMPAT_SHIM_DIR_NAME
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim_path = shim_dir / "sitecustomize.py"
    content = "\n".join(
        [
            "def _patch_legacy_maafw_resource():",
            "    try:",
            "        import maa.resource as maa_resource_module",
            "        if hasattr(maa_resource_module, 'resource'):",
            "            return",
            "        from maa.agent.agent_server import AgentServer",
            "        maa_resource_module.resource = AgentServer",
            "    except Exception:",
            "        pass",
            "",
            "_patch_legacy_maafw_resource()",
            "",
        ]
    )
    try:
        if shim_path.read_text(encoding="utf-8") == content:
            return shim_dir
    except (FileNotFoundError, OSError, UnicodeError):
        pass

    temporary_path = shim_path.with_name(f"{shim_path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(shim_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return shim_dir


def _prepare_project_python_env(
    python_exe: str,
    project_path: Path,
    log: Callable[[str], None],
    *,
    lenient: bool = False,
) -> str | None:
    """检查项目自带 Python 能不能起 MaaFW Agent；返回宽松放行时的原因，其余返回 None。

    三个调用方三种口径（``lenient`` 缺省严格，漏改的调用点不会被放宽）：

    - **运行时**（worker 起 agent 前、宿主运行前 / 运行后的环境确认）传 ``lenient=True``：
      「报错照跑」。检查不管因为什么失败（缺模块、超时、DLL 加载失败、解释器坏了），先照常
      尝试补装 binding，复检仍失败就写一行醒目的警告（原因照原文）、照常起 agent。原因记进
      ``healthWarnings``：这次结果不当「运行环境已就绪」写缓存；agent 随后退出时 worker 把它
      带进最终报错，用户不用翻前面的日志。
    - **更新预检**严格：它决定新版本换不换上来，放宽就会让缺模块的坏版本顶掉能用的旧版本、
      之后每次运行都失败。只有「缺模块、项目带自装材料、补装前完全没有 binding」三条同时满足
      才放行（首次启动自己装依赖的项目），其余照旧拦。
    - **编辑页手动准备**严格（同一套规则）：失败照旧报出来。
    """

    log(f"[Python环境] 检测项目 Python: {python_exe}")
    test_env = _build_project_python_probe_env(python_exe, project_path)
    healthy, reason = _check_project_python_health(
        python_exe,
        cwd=str(project_path),
        env=test_env,
        log=log,
    )
    if healthy:
        _repin_project_python_binding(python_exe, project_path, test_env, log)
        return None

    # 原因放第一行：任务结果与预检失败通知只取报错的第一行，还各自再截 200 / 120 字，
    # 所以项目目录换成 <项目>，免得长安装路径把原因挤掉。
    reason = _project_relative_text(reason, project_path)
    # 放行判据之一：补装之前 site-packages 里根本没有 binding。补装失败后可能留下半装的
    # 东西，不能拿那时的状态判。
    binding_absent = _project_python_binding_absent(python_exe)
    if (lenient or _is_missing_module_failure(reason)) and (
        _repin_project_python_binding(
            python_exe, project_path, test_env, log, install_missing=True
        )
    ):
        # 缺的正是 binding（换版本后视图不带它，见 _repin_project_python_binding）：按原生库
        # 版本补装上了，再检查一次。补装没做成（不是副本、没有原生库、装不上）与钉回失败
        # 一样只记日志，接着走下面的放行判据。宽松模式不管失败原因都先试这一步。
        healthy, reason = _check_project_python_health(
            python_exe,
            cwd=str(project_path),
            env=test_env,
            log=log,
        )
        if healthy:
            return None
        reason = _project_relative_text(reason, project_path)
    materials = (
        describe_self_install_materials(project_path)
        if binding_absent and _is_missing_module_failure(reason)
        else None
    )
    if materials is not None:
        # 「agent 第一次启动时自己装依赖」的项目（MaaDuDuL、MaaTOT 的 pip install -r
        # requirements.txt，MaaStarResonance 的 get-pip.py + deps/*.whl）：依赖还没装，探针
        # 必然导入失败，拦下来 agent 就永远没机会装。照常起 agent，由已有的连接预算兜底；
        # MFAA / MXU 对这类项目也是这样。三个条件同时满足才放行：
        # - 失败是「缺模块」（依赖没装的样子）：原生库加载失败、协议对不上之类照旧拦，别让它们
        #   拖到连接超时才暴露；
        # - 项目带自装材料（requirements.txt / pyproject.toml、*.whl、get-pip.py）；
        # - 补装之前自带解释器的 site-packages 里根本没有 binding（没有 maafw-*.dist-info，也
        #   没有 maa/）。这几个项目第一次运行和换版本后（视图不带 binding）都是这个样子；出厂
        #   就带 binding 的（M9A、MaaStellaSora、MaaFgo、MaaNTE 也都有 requirements.txt）缺
        #   别的模块是真坏了，照旧拦，更新预检（走同一个函数）也照旧拦下坏版本。
        #
        # 装包不写穿共用载荷（2026-10-13 用 import_embedded_project / audit_view 在合成项目上
        # 核实）：视图里的目录都是真目录，≥ 64 KB 的出厂文件才是载荷 / 共用库的硬链接。新建
        # 文件是新 inode；先写临时文件再改名替换（pip 写 RECORD、编 pyc）只换视图里的目录项；
        # pip 装 wheel 时 File.save() 对已存在的目标先 unlink 再写、卸载是改名挪走再删，同样
        # 碰不到载荷。只有不先 unlink 的原地覆盖会写穿，pip 不这么做，运行收尾的写穿巡检
        # 照旧兜底。换版本后：agent 新装的包作为视图私有文件带过去，被它替换过的出厂文件以
        # 新版本为准；site-packages 里的 maa / maafw-*.dist-info 按既有规则不带，下次准备先按
        # 原生库版本补装 binding（上面），补装不成才落到这里放行，agent 自己按它的判据重装。
        log(
            "[Python环境] 项目自带 Python 现在还导入不了 MaaFW Agent 模块"
            f"（{reason}）；项目带着自己的依赖安装材料（{materials}），按项目的写法由 "
            "Agent 第一次启动时自己安装依赖，照常启动 Agent"
        )
        return reason if lenient else None
    if lenient:
        # 运行时「报错照跑」（见函数说明）：原因照原文，只加一行醒目的警告，不拦。
        log(
            "[Python环境] 【警告】项目自带 Python 运行前检查没通过："
            f"{reason}；照常启动 Agent，如果 Agent 随后退出，多半就是这个原因"
        )
        return reason
    # 排障说明只进详情日志：面板与 toast 整段显示报错（pre-wrap），用户照着做不了的
    # 步骤与写给开发者的说明会把失败原因挤掉。
    log(
        f"{DETAIL_LOG_PREFIX}[Python环境] 项目自带 Python 健康检查失败；检查项是该解释器"
        "能否导入 maa.agent.agent_server。项目 Python 属于 release 内容，AUTO-MAS 不要求"
        "其提供 pip；只在自己的内嵌副本里修它的 maafw binding 版本。"
    )
    # 处理建议按两种情况写：导入后目录锁定，「重新下载解压」照着做不了。本机副本这边，
    # 严格检查只在缺模块时补装 binding（上面），所以重试能修好的是补装没做成的那种；视图
    # 只在 interface.json 不在时按载荷重建，其余文件坏了要等换版本时整棵重建。
    raise MaaFWAgentEnvError(
        f"项目 Python 或 MaaFW Agent 模块不可用（{reason}）\n"
        f"  Python 路径: {python_exe}\n"
        "  处理建议: 本机这份副本的问题（如补装 maafw 时没联网）检查网络后重试即可；"
        "项目包本身就缺这个模块时，等项目发布新版本后更新，或反馈给项目作者"
    )


def _project_python_binding_absent(python_exe: str | Path) -> bool:
    """自带解释器的 site-packages 里既没有 ``maafw-*.dist-info``，也没有 ``maa/``。"""

    if any(True for _ in _iter_maafw_dist_info_groups(python_exe)):
        return False
    root = Path(python_exe).parent
    for site in (
        root / "Lib" / "site-packages",
        *sorted(root.glob("lib/python*/site-packages")),
    ):
        try:
            if (site / "maa").exists():
                return False
        except OSError:
            return False
    return True


def _is_missing_module_failure(reason: str) -> bool:
    """健康检查失败的那一行是不是「缺模块」（依赖还没装的样子）。"""

    return reason.startswith("ModuleNotFoundError") or "No module named" in reason


def project_python_maafw_version(python_exe: str | Path) -> str | None:
    """项目自带解释器里装的 maafw binding 版本（读 dist-info 目录名，不起进程）。

    同一 site-packages 里可能残留多个 ``maafw-*.dist-info``（M9A 发行包就同时带着
    5.12.3 与 5.13.0，旧的是升级没卸干净留下的）：取 PEP 440 最高的那个。按名字
    排序取第一个会读成旧版本，于是每次准备环境都去「钉回」一个本来就对的 binding，
    重装出来的文件脱离共用库。
    """

    for matches in _iter_maafw_dist_info_groups(python_exe):
        versions = [
            text
            for text in (
                match.name[len("maafw-") : -len(".dist-info")] for match in matches
            )
            if text
        ]
        if not versions:
            continue
        parsed: list[tuple[Version, str]] = []
        for text in versions:
            try:
                parsed.append((Version(text), text))
            except InvalidVersion:
                continue
        if parsed:
            return max(parsed, key=lambda item: item[0])[1]
        return versions[0]
    return None


def _iter_maafw_dist_info_groups(python_exe: str | Path):
    """按查找顺序逐个 site-packages 给出其中的 ``maafw-*.dist-info``（排好序；空的跳过）。"""

    root = Path(python_exe).parent
    for site in (
        root / "Lib" / "site-packages",
        *sorted(root.glob("lib/python*/site-packages")),
    ):
        try:
            matches = sorted(site.glob("maafw-*.dist-info"))
        except OSError:
            continue
        if matches:
            yield matches


def _stale_maafw_dist_infos(python_exe: str | Path) -> list[Path]:
    """与 :func:`project_python_maafw_version` 同一个 site-packages 里、版本不是最高的
    那些 ``maafw-*.dist-info``——升级没卸干净留下的旧安装记录。

    它们会让 pip 与我们对「装的是哪个版本」各说各的：pip 按目录顺序取第一个记录，
    我们取最高版本。钉回前不清掉，``pip install maafw==<原生库版本>`` 要么把同版本的旧
    记录当成已装好、什么都不做（M9A v4.9.0 带 5.12.3 + 5.13.0 两份，原生库是 5.12.3 时
    就是这样），要么只卸掉旧记录、留下更高的那份；两种结果下次准备读到的都还不是原生库
    版本，于是每次准备都重跑钉回，改了记录集合的那次还会被当成并发改动拒绝缓存。
    """

    for matches in _iter_maafw_dist_info_groups(python_exe):
        parsed: list[tuple[Version, Path]] = []
        for match in matches:
            text = match.name[len("maafw-") : -len(".dist-info")]
            try:
                parsed.append((Version(text), match))
            except InvalidVersion:
                continue
        if len(parsed) < 2:
            return []
        newest = max(parsed, key=lambda item: item[0])[1]
        return [path for _, path in parsed if path != newest]
    return []


def _is_embedded_copy(project_path: Path) -> bool:
    """项目目录是不是 AUTO-MAS 自己的内嵌副本（``data/mfw/<脚本 id>``）。"""

    try:
        project_path.resolve().relative_to(
            Path.cwd().joinpath(*EMBEDDED_COPIES_DIR_PARTS).resolve()
        )
    except (ValueError, OSError):
        return False
    return True


def _repin_project_python_binding(
    python_exe: str,
    project_path: Path,
    env: dict[str, str],
    log: Callable[[str], None],
    *,
    install_missing: bool = False,
) -> bool:
    """自带解释器里的 maafw binding 与自带原生库版本不一致时，在副本里把它钉回去。

    runner 加载的是项目自带的原生库（``project_maafw_runtime_path``），agent 侧的 binding
    必须与之同版本，否则 AgentServer/Client 协议对不上、只表现为「连接超时」。项目自己的
    部署脚本会把 binding ``pip install --upgrade`` 到 PyPI 最新（Maa_bbb v1.12.8 实测升到
    5.13.1/协议 8，原生库还是 5.11.1/协议 7）。**只动内嵌副本**：那是 AUTO-MAS 自己铺的；
    用户手上的项目目录仍然一个字节不碰，只把原因说清。任何一步失败只记日志，不拦准备。

    ``install_missing``：自带解释器里压根没装 binding 时也按原生库版本补装（目标版本只看
    原生库，与已装版本无关）。换版本时视图不带 site-packages 里的 binding（见
    ``embedded_project._is_maafw_binding_path``），而「首次启动自己装依赖」的项目常有自己的
    「已装过」标记（MaaTOT 的 ``config/pip_config.json``），不会再装，agent 一 import maa 就退出。
    只由健康检查报缺模块的那条路传：健康时 maa 导得进来，没有 dist-info 也不去动它。

    返回装完之后 binding 是否与原生库同版本（没动手、动手失败都是 False）。
    """

    from app.task.MaaFW.tools.core.runner.environment import (
        probe_bundled_maafw_version,
    )

    installed = project_python_maafw_version(python_exe)
    native = probe_bundled_maafw_version(project_path)
    if not native or (not installed and not install_missing):
        return False
    if installed:
        try:
            same = Version(installed) == Version(native)
        except InvalidVersion:
            same = installed == native
        if same:
            return False
        mismatch = (
            f"项目自带 Python 里的 maafw 是 {installed}，"
            f"项目自带的 MaaFramework 原生库是 {native}"
        )
        action = f"把副本里的 binding 钉回 {native}"
    else:
        mismatch = f"项目自带 Python 里没有装 maafw binding，项目自带的 MaaFramework 原生库是 {native}"
        action = f"在副本里按原生库版本补装 binding {native}"
    if not _is_embedded_copy(Path(project_path)):
        if installed:
            log(
                f"[Python环境] {mismatch}，Agent 协议会对不上；这是项目目录，AUTO-MAS 不改它，"
                "请更新项目或自行把 binding 版本对齐"
            )
        else:
            log(f"[Python环境] {mismatch}；这是项目目录，AUTO-MAS 不往里装")
        return False
    log(f"[Python环境] {mismatch}，{action}")
    # 残留的旧安装记录先挪开（不删）：钉回成功才丢，失败就原样放回。dist-info 集合是
    # 环境指纹的输入，失败时若集合变了、版本又没对上，准备会被当成并发改动拒绝缓存——
    # 离线时本来能过的项目（M9A v4.9.0 出厂形态）会因此每次都失败。
    stash, moved = _stash_stale_maafw_dist_infos(python_exe, Path(project_path), log)
    if moved:
        log(
            f"[Python环境] 先把副本里残留的旧 maafw 安装记录 "
            f"{', '.join(original.name for original, _ in moved)} 挪开（实际装的是 "
            f"{installed}），否则 pip 会认错已装版本"
        )
    ok, detail = _pip_install(
        python_exe, [f"maafw=={native}"], cwd=str(project_path), env=env, log=log
    )
    pinned = project_python_maafw_version(python_exe) if ok else None
    try:
        pinned_ok = pinned is not None and Version(pinned) == Version(native)
    except InvalidVersion:
        pinned_ok = pinned == native
    if ok and pinned_ok:
        if stash is not None and not remove_tree_best_effort(stash):
            log(f"[Python环境] 挪开的旧 maafw 安装记录没删干净，留在 {stash}")
        return True
    if moved:
        _restore_stashed_dist_infos(moved, log)
    if stash is not None and not remove_tree_best_effort(stash):
        log(f"[Python环境] 临时目录没删干净，留在 {stash}")
    if not ok:
        log(
            f"[Python环境] binding 钉回失败，agent 可能连不上: {output_tail(detail, 200)}"
        )
    else:
        log(
            f"[Python环境] 钉回后读到的 binding 仍是 {pinned or '未知'}，与原生库 {native} "
            "不一致，agent 可能连不上"
        )
    return False


#: 钉回期间暂放旧 maafw 安装记录的目录（副本根下，钉回结束即删）
REPIN_STASH_PREFIX = ".maafw-repin-stash-"


def _stash_stale_maafw_dist_infos(
    python_exe: str, project_path: Path, log: Callable[[str], None]
) -> tuple[Path | None, list[tuple[Path, Path]]]:
    """把 :func:`_stale_maafw_dist_infos` 挪进副本根下的临时目录。

    只挪记录目录本身，不按它的 RECORD 动文件：那些文件现在属于更高的版本，由 pip 按那份
    记录卸。同一卷上是目录改名，目录里的小文件是视图私有的复制件，不写穿载荷。
    返回（临时目录或 None, [(原位置, 暂放位置)]）。
    """

    stale = _stale_maafw_dist_infos(python_exe)
    if not stale:
        return None, []
    stash = project_path / (
        f"{REPIN_STASH_PREFIX}{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    moved: list[tuple[Path, Path]] = []
    for original in stale:
        target = stash / original.name
        try:
            stash.mkdir(parents=True, exist_ok=True)
            os.rename(original, target)
        except OSError as exc:
            log(f"[Python环境] 挪开旧的 maafw 安装记录 {original.name} 失败: {exc}")
            continue
        moved.append((original, target))
    return stash, moved


def _restore_stashed_dist_infos(
    moved: list[tuple[Path, Path]], log: Callable[[str], None]
) -> None:
    """钉回没成：把挪开的记录原样放回，dist-info 集合与指纹回到钉回前。"""

    for original, stashed in moved:
        if original.exists():
            # pip 装出了同名记录（装上了却读不对版本）：以它为准，暂放的这份随临时目录删掉
            log(f"[Python环境] {original.name} 已被 pip 重建，不放回旧记录")
            continue
        try:
            os.rename(stashed, original)
        except OSError as exc:
            log(f"[Python环境] 放回旧的 maafw 安装记录 {original.name} 失败: {exc}")


def _isolated_venv_lock(path: Path) -> threading.RLock:
    """本进程内的那一半锁；准备时用的是 ``venv_share.isolated_venv_guard``（还有锁文件）。"""

    return venv_thread_lock(path)


def _resolve_isolated_venv_target(
    plan: MaaFWAgentCommandPlan,
    project_path: Path,
    log: Callable[[str], None],
    *,
    runner_maafw_version: str | None,
) -> tuple[Path, str | None]:
    """这次准备用哪个目录，以及建计划时（不知道 runner 版本）会算出的键名。

    共用目录（依赖清单 + maafw 版本 + 宿主身份）已经建好就用它——同样依赖的视图共用的
    就是这一份。还没建、而本视图升级前按项目路径建的老目录老规则下还能接着用（项目路径、
    interface、依赖清单都没变）时沿用老目录：升级后第一跑不重建、不联网；之后项目一更新
    或别的视图建好了共用目录就换过去，老目录没人引用了由启动期回收。其余都建共用目录。
    读不了依赖清单照原样抛 ``MaaFWAgentEnvError``（以前在准备里同样抛）。
    """

    planned = Path(plan.isolatedVenvPath) if plan.isolatedVenvPath else None
    root = (
        planned.parent.resolve()
        if planned is not None
        else resolve_agent_venv_root(None)
    )
    shared = root / shared_venv_name(
        shared_venv_key_inputs(project_path, runner_maafw_version=runner_maafw_version)
    )
    if not runner_maafw_version:
        plan_name: str | None = shared.name
    else:
        try:
            plan_name = shared_venv_name(shared_venv_key_inputs(project_path))
        except Exception:  # noqa: BLE001 - 只用于建计划时的对照，算不出来不记
            plan_name = None
    if _is_valid_venv_path(shared):
        return shared, plan_name
    legacy = root / legacy_isolated_venv_name(project_path)
    if _legacy_isolated_venv_reusable(
        legacy, project_path, runner_maafw_version=runner_maafw_version
    ):
        log(
            "[Python环境] 沿用升级前为该项目建的隔离 venv（依赖未变，不重建）；"
            f"项目依赖变化或同样依赖的共用 venv 建好后改用共用的: {legacy}"
        )
        return legacy, plan_name
    return shared, plan_name


def _legacy_isolated_venv_reusable(
    venv_path: Path, project_path: Path, *, runner_maafw_version: str | None
) -> bool:
    """老规则下这份按路径建的 venv 会被直接复用吗（与升级前的判据完全相同）。"""

    if not _is_valid_venv_path(venv_path):
        return False
    try:
        manifest = json.loads(
            (venv_path / AGENT_ENV_MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except Exception:  # noqa: BLE001 - 读不出来老规则下也是重建
        return False
    if not isinstance(manifest, dict):
        return False
    expected = build_agent_env_manifest(
        project_path, runner_maafw_version=runner_maafw_version
    )
    return _isolated_venv_mismatch(venv_path, manifest, expected) is None


def _retarget_isolated_plan(
    plan: MaaFWAgentCommandPlan, venv_path: Path, log: Callable[[str], None]
) -> None:
    previous = plan.isolatedVenvPath or ""
    target = str(venv_path)
    if previous and os.path.normcase(previous) == os.path.normcase(target):
        return
    python = str(venv_python_exe(venv_path))
    plan.isolatedVenvPath = target
    plan.executable = python
    plan.executableExists = Path(python).exists()
    if plan.command:
        plan.command[0] = python
    if previous and plan.fallbackReason:
        plan.fallbackReason = plan.fallbackReason.replace(previous, target)
    log(
        f"[Python环境] Agent {plan.childExec} 的隔离 venv 按准备时的依赖与 maafw 版本改用: "
        f"{target}（建计划时是 {previous or '未指定'}）"
    )


def _record_isolated_venv_ref(
    venv_path: Path,
    project_path: Path,
    plan_name: str | None,
    log: Callable[[str], None],
) -> None:
    """记下本视图这次用的目录：回收按它算存活，建计划时按它找准备时实际用的那份。"""

    try:
        write_venv_ref(
            venv_path.parent,
            project_path,
            venv_name=venv_path.name,
            plan_name=plan_name,
        )
    except Exception as exc:  # noqa: BLE001 - 记不下只影响回收与下次建计划，不拦运行
        log(f"[Python环境] 记录隔离 venv 的使用者失败（不影响本次运行）: {exc}")


def _report_agent_progress(
    callback: Callable[[dict[str, object]], None] | None,
    *,
    status: str,
    message: str,
    percent: float,
    completed: int,
    total: int,
) -> None:
    if callback is None:
        return
    try:
        callback(
            {
                "stage": "preparing_agents",
                "status": status,
                "message": message,
                "percent": percent,
                "completed": completed,
                "total": total,
            }
        )
    except Exception:
        # 进度只是旁观者，不能拖垮 Agent 环境准备；但要留痕，否则回调里的
        # ``no running event loop`` 这类错误就此消失。
        logger.warning("MaaFW Agent 环境进度回调失败: %s", status, exc_info=True)


def _prepare_isolated_venv_env(
    agent_plan: MaaFWAgentCommandPlan,
    project_path: Path,
    log: Callable[[str], None],
    *,
    bootstrap_python: str | None,
    install_dependencies: bool,
    runner_maafw_version: str | None = None,
) -> Path:
    if not agent_plan.isolatedVenvPath:
        raise MaaFWAgentEnvError("隔离 venv 路径未提供，无法创建隔离环境")

    venv_path = Path(agent_plan.isolatedVenvPath).resolve()
    python_exe = (
        agent_plan.command[0] if agent_plan.command else str(venv_python_exe(venv_path))
    )

    log(f"[Python环境] 准备隔离 venv: {venv_path}")
    if is_shared_venv_name(venv_path.name):
        expected_key = build_agent_env_manifest(
            project_path, runner_maafw_version=runner_maafw_version
        )["venvKey"]
        if venv_path.name != expected_key:
            # 共用目录名就是键：对不上说明这份是别的依赖组合的，按本项目的判据重建会把
            # 别人正在用的删掉。正常路径上 prepare_agent_envs 已经改写过计划，走不到这里。
            raise MaaFWAgentEnvError(
                f"隔离 venv 与本项目的依赖不符（应为 {expected_key}），"
                f"不改动其他项目共用的 venv: {venv_path}"
            )
    had_valid_venv = _is_valid_venv_path(venv_path)
    if _should_rebuild_isolated_venv(
        venv_path, project_path, log, runner_maafw_version=runner_maafw_version
    ):
        _reset_isolated_venv(venv_path, log)
        had_valid_venv = False
    _ensure_isolated_venv(venv_path, log, bootstrap_python=bootstrap_python)
    write_agent_compat_shims(venv_path)

    test_env = _build_agent_env_for_pip(project_path)
    test_env["PYTHONPATH"] = str(project_path)

    if not _check_pip_health(python_exe, cwd=str(project_path), env=test_env, log=log):
        log("[Python环境] 隔离 venv pip 异常，尝试 ensurepip 修复...")
        if not _try_ensurepip(python_exe, cwd=str(project_path), env=test_env, log=log):
            raise MaaFWAgentEnvError(f"隔离 venv pip 无法自动修复: {python_exe}")

    if had_valid_venv and _is_isolated_venv_manifest_current(
        venv_path, project_path, runner_maafw_version=runner_maafw_version
    ):
        log("[Python环境] 隔离 venv 依赖清单未变化，跳过 pip install")
        return venv_path

    if install_dependencies:
        packages = _load_project_agent_requirements(
            project_path, runner_maafw_version=runner_maafw_version
        )
        parsed_requirements = read_requirements_file(project_path / "requirements.txt")
        if parsed_requirements is not None and parsed_requirements.ignored_options:
            log(
                "[Python环境] requirements.txt 里的选项行不传给 pip（索引由 AUTO-MAS 的"
                "镜像候选决定），已忽略: "
                + ", ".join(parsed_requirements.ignored_options)
            )
        log(f"[Python环境] 隔离 venv 安装项目依赖: {', '.join(packages)}")
        installed, failure_detail = _pip_install(
            python_exe, packages, cwd=str(project_path), env=test_env, log=log
        )
        if not installed:
            # 原来只报解释器路径，用户拿它做不了任何事，真实原因还只写进一个
            # 没人持久化的 list。带上原因，现有告警条就能自己说明白。
            raise MaaFWAgentEnvError(
                f"隔离 venv 依赖安装失败: {failure_detail or python_exe}"
            )
    else:
        log("[Python环境] 当前调用禁用依赖安装，仅写入隔离 venv manifest")

    _write_isolated_venv_manifest(
        venv_path, project_path, runner_maafw_version=runner_maafw_version
    )
    return venv_path


def _is_valid_venv_path(venv_path: Path) -> bool:
    if not (
        venv_python_exe(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()
    ):
        return False
    # 文件都在不代表能用：引导用的基解释器（受管模式下常是 sys.executable
    # 所在的监督器管理 venv）事后被删掉重建过的话，这个 venv 也已经失效。
    return not venv_base_python_missing(venv_path)


def _ensure_isolated_venv(
    venv_path: Path,
    log: Callable[[str], None],
    *,
    bootstrap_python: str | None,
) -> None:
    if _is_valid_venv_path(venv_path):
        log(f"[Python环境] 隔离 venv 已存在: {venv_path}")
        return

    if venv_path.exists():
        _reset_isolated_venv(venv_path, log)

    venv_path.parent.mkdir(parents=True, exist_ok=True)
    python = bootstrap_python if bootstrap_python else _venv_bootstrap_python()
    if python is not None and bootstrap_python and not _python_supports_venv(python):
        # 调用方指定的引导解释器（如便携 embeddable Python）缺 venv，回退到自动挑选
        log(f"[Python环境] 指定引导 Python 缺少 venv 模块，改为自动挑选: {python}")
        python = _venv_bootstrap_python()

    if python is None:
        _create_venv_with_uv(venv_path, log)
    else:
        log(f"[Python环境] 创建隔离 venv: {venv_path} (引导 Python: {python})")
        try:
            result = subprocess.run(
                [python, "-m", "venv", str(venv_path)],
                capture_output=True,
                timeout=PIP_INSTALL_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                # 引导解释器同样不能被宿主 PYTHONHOME / PYTHONPATH 带偏。
                env=strip_host_python_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise MaaFWAgentEnvError(
                f"创建隔离 venv 超时 ({PIP_INSTALL_TIMEOUT}s): {venv_path}"
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise MaaFWAgentEnvError(
                f"创建隔离 venv 失败 (exit={result.returncode}): {output_tail(detail, 500)}"
            )
    if not _is_valid_venv_path(venv_path):
        raise MaaFWAgentEnvError(f"创建隔离 venv 后结构不完整: {venv_path}")
    log(f"[Python环境] 隔离 venv 创建成功: {venv_path}")


def _create_venv_with_uv(venv_path: Path, log: Callable[[str], None]) -> None:
    """所有候选解释器都缺 venv 时的兜底：用 uv 建环境（必要时自取 managed Python）。"""
    uv_exe = _find_uv_executable()
    if uv_exe is None:
        raise MaaFWAgentEnvError(
            "创建隔离 venv 失败：可用的 Python 均不含 venv 模块（便携版通常为 "
            "embeddable 发行版），且未找到 uv 兜底。请安装完整 Python 或提供 uv。"
        )

    log(f"[Python环境] 引导 Python 均缺少 venv 模块，改用 uv 创建: {venv_path}")
    try:
        result = subprocess.run(
            [uv_exe, "venv", "--seed", "--no-config", str(venv_path)],
            capture_output=True,
            timeout=UV_VENV_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=strip_host_python_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise MaaFWAgentEnvError(
            f"uv 创建隔离 venv 超时 ({UV_VENV_TIMEOUT}s): {venv_path}"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise MaaFWAgentEnvError(
            f"uv 创建隔离 venv 失败 (exit={result.returncode}): {output_tail(detail, 500)}"
        )


def _should_rebuild_isolated_venv(
    venv_path: Path,
    project_path: Path,
    log: Callable[[str], None],
    *,
    runner_maafw_version: str | None = None,
) -> bool:
    if venv_path.exists() and venv_base_python_missing(venv_path):
        log(
            f"[Python环境] 隔离 venv 的基解释器已不存在（pyvenv.cfg 的 home 已"
            f"失效），将重建: {venv_path}"
        )
        return True
    if venv_path.exists() and not _is_valid_venv_path(venv_path):
        log("[Python环境] 隔离 venv 不完整，将重建")
        return True
    if not _is_valid_venv_path(venv_path):
        return False

    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log("[Python环境] 隔离 venv 缺少依赖清单，将重建")
        return True
    except Exception as exc:
        log(f"[Python环境] 隔离 venv 依赖清单异常，将重建: {exc}")
        return True

    expected = build_agent_env_manifest(
        project_path, runner_maafw_version=runner_maafw_version
    )
    reason = _isolated_venv_mismatch(venv_path, manifest, expected)
    if reason is not None:
        log(reason)
        return True
    return False


def _isolated_venv_mismatch(
    venv_path: Path, manifest: object, expected: dict[str, object]
) -> str | None:
    """这份 venv 还能不能给本项目用；不能时返回要写进日志的那一行。

    共用目录（``maafw_venv_<16hex>``）只看键与依赖清单：项目路径、interface 是建它的那个
    视图的，别的视图、依赖没变的新版本照样能用，按它们重建会删掉别人正在用的 venv。
    其余（升级前按项目路径建的老目录、调用方直接指定的目录）照旧按项目路径 + interface +
    依赖清单判定。
    """

    if not isinstance(manifest, dict):
        return "[Python环境] 隔离 venv 依赖清单异常，将重建"
    if is_shared_venv_name(venv_path.name):
        if manifest.get("venvKey") != expected["venvKey"]:
            return "[Python环境] 隔离 venv 的共用键与依赖清单不符，将重建"
        if manifest.get("requirementsHash") != expected["requirementsHash"]:
            return "[Python环境] MaaFW 项目 requirements 已变化，将重建隔离 venv"
        return None
    if manifest.get("projectPath") != expected["projectPath"]:
        return "[Python环境] 隔离 venv 项目路径已变化，将重建"
    if manifest.get("interfaceHash") != expected["interfaceHash"]:
        return "[Python环境] MaaFW 项目 interface 已变化，将重建隔离 venv"
    if manifest.get("requirementsHash") != expected["requirementsHash"]:
        return "[Python环境] MaaFW 项目 requirements 已变化，将重建隔离 venv"
    return None


def _reset_isolated_venv(venv_path: Path, log: Callable[[str], None]) -> None:
    if venv_path.parent.name != "maafw_agent_venvs" or not venv_path.name.startswith(
        "maafw_venv_"
    ):
        raise MaaFWAgentEnvError(f"拒绝重建非托管隔离 venv: {venv_path}")
    # 先改名再删：venv 可能被别的视图共用，正有 agent 从里面跑着时 Windows 不让改名，
    # 这时报错、不动它——以前 rmtree(ignore_errors) 会删掉一半、留个谁都用不了的残骸。
    # 改名成功后删不干净的残留同前缀，启动期按孤儿回收。
    trash = venv_path.with_name(
        f"{venv_path.name}{VENV_TRASH_MARKER}{uuid.uuid4().hex[:8]}"
    )
    try:
        os.rename(venv_path, trash)
    except FileNotFoundError:
        trash = None
    except OSError as exc:
        raise MaaFWAgentEnvError(
            f"隔离 venv 需要重建，但它正被占用（可能有使用同样依赖的脚本正在运行），"
            f"等那边运行结束后再试: {venv_path} - {exc}"
        ) from exc
    if trash is not None:
        shutil.rmtree(trash, ignore_errors=True)
    log(f"[Python环境] 已清理旧隔离 venv: {venv_path}")


def _is_isolated_venv_manifest_current(
    venv_path: Path, project_path: Path, *, runner_maafw_version: str | None = None
) -> bool:
    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    expected = build_agent_env_manifest(
        project_path, runner_maafw_version=runner_maafw_version
    )
    return _isolated_venv_mismatch(venv_path, manifest, expected) is None


def _write_isolated_venv_manifest(
    venv_path: Path, project_path: Path, *, runner_maafw_version: str | None = None
) -> None:
    manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(
            build_agent_env_manifest(
                project_path, runner_maafw_version=runner_maafw_version
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_project_agent_requirements(
    project_path: Path, *, runner_maafw_version: str | None = None
) -> list[str]:
    # 延迟导入：``runner`` 的包初始化会 import ``run_plan``，而
    # ``run_plan`` 反过来 import 本包，写成模块级导入会成环。
    from app.task.MaaFW.tools.core.runner.environment import (
        pin_agent_maafw_requirement,
        resolve_project_maafw_requirement,
    )

    # 清单逐条当独立参数交给 pip / uv（没有 -r 那一层），所以按 pip 的规则先洗一遍：
    # BOM、行内注释、续行、整行选项与 --hash 都会让原样照抄的那一条装不上。
    try:
        parsed = read_requirements_file(project_path / "requirements.txt")
    except RequirementsFileError as exc:
        # -r 引用的子清单读不了 / 越界、用了不支持的 -c / -e：报错，不能少装了依赖还报就绪
        raise MaaFWAgentEnvError(str(exc)) from exc
    declared = parsed is not None
    packages: list[str] = list(parsed.requirements) if parsed is not None else []

    normalized = {item.split(";", 1)[0].strip().lower() for item in packages}
    if not any(item.startswith(AGENT_BOOTSTRAP_PACKAGE) for item in normalized):
        packages.append(AGENT_BOOTSTRAP_PACKAGE)
    # agent 侧的 binding 必须与 runner 加载的原生库同版本，否则 AgentServer 与
    # AgentClient 的协议版本对不上，握手被拒、在我们这边只表现为连不上。

    pinned = pin_agent_maafw_requirement(
        project_path, packages, runner_maafw_version=runner_maafw_version
    )
    if not declared:
        # 压根没有 requirements.txt 的 Python agent：MFW-PyQt6 的「嵌入式 Agent」
        # 模式（FOS 这类，CFA_setting.json 里 embedded=true）把 maa 与 numpy 冻进了
        # 外壳自己的程序里，发行包不写依赖。这份 venv 只会给 Python agent 用，里面
        # 至少得有跟项目自带原生库同版本的 binding，否则 agent import maa 当场退出。
        # 项目没自带原生库时用 runner 这次实际用的版本；两样都拿不到才原样。
        requirement = resolve_project_maafw_requirement(
            project_path, runner_maafw_version=runner_maafw_version
        )
        if requirement is not None:
            pinned.append(requirement)
    return pinned


def _project_agent_requirements_hash(
    project_path: Path, *, runner_maafw_version: str | None = None
) -> str:
    return _requirements_hash(
        _load_project_agent_requirements(
            project_path, runner_maafw_version=runner_maafw_version
        )
    )


def _requirements_hash(requirements: list[str]) -> str:
    payload = json.dumps(requirements, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project_interface_hash(project_path: Path) -> str:
    for name in ("interface.json", "interface.jsonc"):
        path = project_path / name
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _build_agent_env_for_pip(project_path: Path) -> dict[str, str]:
    # 剔除名单与运行池 / worker 共用；隔离 venv 里的 pip 只认项目根这一条 PYTHONPATH。
    env = strip_host_python_environment()
    env["PYTHONPATH"] = str(project_path)
    set_project_pycache_prefix(env, project_path)
    return env


#: agent 侧 ``from maa.agent.agent_server import AgentServer`` 要加载的库，与
#: ``MaaFramework.dll`` 同在项目自带的原生库目录里时才算那份可用（与 M9A 的判据一致）。
PROJECT_AGENT_SERVER_DLL_NAME = "MaaAgentServer.dll"


def _bundled_maa_bin_missing(python_exe: str | Path) -> bool:
    """自带解释器里有 maa 包、却没有 wheel 自带的 ``maa/bin``。找不到 maa 包时不算缺。"""

    root = Path(python_exe).parent
    for site in (
        root / "Lib" / "site-packages",
        *sorted(root.glob("lib/python*/site-packages")),
    ):
        package = site / "maa"
        if (package / "__init__.py").is_file():
            return not (package / "bin").is_dir()
    return False


def _build_project_python_probe_env(
    python_exe: str, project_path: Path
) -> dict[str, str]:
    """项目自带 Python 健康检查的环境：pip 那份，外加 agent 自己会设的原生库目录。

    M9A 的发行包不在自带解释器的 ``site-packages/maa/bin`` 里再放一份原生库，agent 在
    ``import maa`` 之前自己把 ``MAAFW_BINARY_PATH`` 指到 ``runtimes/<rid>/native``
    （M9A 的 ``agent/maafw_paths.py``）。检查直接 ``import maa``，这个变量又被剔除了，
    binding 就去开不存在的 ``maa/bin``、抛 ``FileNotFoundError``，把能跑的副本判成坏的，
    更新预检也因此永远过不去。所以 ``maa/bin`` 不在、项目自带的原生库又齐时，检查
    也指过去；``maa/bin`` 在时不动，照旧用 wheel 自带那份。

    问题包导出（``frontend/electron/services/maafwProjectRuntimeProbe.ts``）按同一判据
    再跑一次这个检查，改判据时两边一起改。
    """

    env = _build_agent_env_for_pip(project_path)
    runtime = project_python_agent_binary_path(python_exe, project_path)
    if runtime is not None:
        env["MAAFW_BINARY_PATH"] = str(runtime)
    return env


def project_python_agent_binary_path(
    python_exe: str | Path, project_path: Path
) -> Path | None:
    """项目自带解释器的 agent 该经 ``MAAFW_BINARY_PATH`` 用的原生库目录；不该设时 None。

    ``maa/bin`` 不在、runner 用的是项目自带原生库（``project_maafw_runtime_path``）且那里
    有 ``MaaAgentServer.dll`` 时，就是 runner 那份。健康检查与 runner 起 agent
    （``runner._build_agent_env``）都从这里取，两边永远指同一个目录：M9A 的 agent 已设
    这个变量时一律沿用，不再自己按 ``runtimes/`` → ``maafw/`` 的顺序找——两份原生库并存
    时它找到的未必是 runner 选的那份，协议版本不同就握手失败。
    """

    if not _bundled_maa_bin_missing(python_exe):
        return None

    from app.task.MaaFW.tools.core.runner.environment import (
        project_maafw_runtime_path,
    )

    runtime = project_maafw_runtime_path(project_path)
    if runtime is not None and (runtime / PROJECT_AGENT_SERVER_DLL_NAME).is_file():
        return runtime
    return None


def _project_relative_text(text: str, project_path: Path) -> str:
    """把文本里的项目目录（大小写不敏感）换成 ``<项目>``。

    OSError 系异常用 repr 显示路径，反斜杠成对，原样、正斜杠、成对反斜杠三种都认。
    """

    root = str(project_path)
    if not root:
        return text
    for variant in dict.fromkeys(
        (root.replace("\\", "\\\\"), root, root.replace("\\", "/"))
    ):
        text = re.sub(
            re.escape(variant), lambda _match: "<项目>", text, flags=re.IGNORECASE
        )
    return text


def _last_output_line(text: str) -> str:
    """输出的最后一个非空行：traceback 里就是异常类型与消息。"""

    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _check_pip_health(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "--version"],
            capture_output=True,
            timeout=PIP_HEALTH_CHECK_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            log(
                f"[Python环境] pip --version 失败 (exit={result.returncode}): {output_tail(detail, 500)}"
            )
            return False

        install_check = subprocess.run(
            [
                python_exe,
                "-c",
                "from pip._internal.commands.install import InstallCommand; print('install command OK')",
            ],
            capture_output=True,
            timeout=PIP_HEALTH_CHECK_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if install_check.returncode == 0:
            log(f"[Python环境] pip 健康: {result.stdout.strip()}")
            return True

        detail = (install_check.stderr or install_check.stdout or "").strip()
        if "backports.zstd" in detail or "ZstdError" in detail:
            log("[Python环境] pip install 子命令加载失败（backports.zstd 冲突）")
        else:
            log(
                f"[Python环境] pip install 检测失败 (exit={install_check.returncode}): {output_tail(detail, 500)}"
            )
        return False
    except subprocess.TimeoutExpired:
        log(f"[Python环境] pip 检测超时 ({PIP_HEALTH_CHECK_TIMEOUT}s)")
        return False
    except Exception as exc:
        log(f"[Python环境] pip 检测异常: {exc}")
        return False


def _check_project_python_health(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    """Probe a project-owned Agent runtime without requiring or invoking pip.

    返回 ``(是否健康, 失败原因)``。失败原因是一行（traceback 的最后一行），进界面与
    报错文案；完整输出逐行带 :data:`DETAIL_LOG_PREFIX` 记下，只进 ``.worker.log`` /
    后端日志，问题包里能看到整段 traceback。
    """

    probe = (
        "import sys; "
        "from maa.agent.agent_server import AgentServer; "
        "print(f'Python {sys.version_info.major}.{sys.version_info.minor}; MaaFW Agent OK')"
    )
    try:
        result = subprocess.run(
            [python_exe, "-c", probe],
            capture_output=True,
            timeout=PROJECT_PYTHON_HEALTH_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        reason = f"健康检查超时 ({PROJECT_PYTHON_HEALTH_TIMEOUT}s)"
        log(f"[Python环境] 项目 Python/Agent {reason}")
        return False, reason
    except Exception as exc:
        reason = f"健康检查异常: {exc}"
        log(f"[Python环境] 项目 Python/Agent {reason}")
        return False, reason

    if result.returncode == 0:
        detail = (result.stdout or "").strip()
        log(f"[Python环境] 项目 Python/Agent 健康: {detail or python_exe}")
        return True, ""

    detail = (result.stderr or result.stdout or "").strip()
    reason = output_tail(_last_output_line(detail), 500) or f"exit={result.returncode}"
    log(
        "[Python环境] 项目 Python/Agent 健康检查失败 "
        f"(exit={result.returncode}): {reason}"
    )
    if detail:
        log(f"{DETAIL_LOG_PREFIX}项目 Python/Agent 健康检查完整输出（{python_exe}）:")
        for line in output_tail(detail, DETAIL_OUTPUT_LIMIT).splitlines():
            log(f"{DETAIL_LOG_PREFIX}{line}")
    return False, reason


def _try_ensurepip(
    python_exe: str,
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> bool:
    log("[Python环境] 修复策略 A (ensurepip)...")
    try:
        result = subprocess.run(
            [python_exe, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            timeout=PIP_INSTALL_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        if result.returncode == 0 and _check_pip_health(
            python_exe, cwd=cwd, env=env, log=log
        ):
            log("[Python环境] ensurepip 修复成功")
            return True
        detail = (result.stderr or result.stdout or "").strip()
        log(f"[Python环境] ensurepip 未成功: {output_tail(detail, 300)}")
    except subprocess.TimeoutExpired:
        log(f"[Python环境] ensurepip 超时 ({PIP_INSTALL_TIMEOUT}s)")
    except Exception as exc:
        log(f"[Python环境] ensurepip 执行异常: {exc}")
    return False


def _pip_index_arg_candidates() -> list[tuple[str, list[str]]]:
    """按序返回 pip 的索引候选 ``(日志标签, 参数)``，与运行池 installer 同源。

    Runtime 经 AUTO_MAS_MIRROR_PACKAGE_INDEX 注入镜像列表；键存在但为空表示
    要求完全离线，此时只跑一次 --no-index，绝不联网（运行池遵守这条契约，
    这里此前不遵守，属于契约漏洞）。用户显式设了 PIP_INDEX_URL 就尊重它，
    不参与候选轮换——参数留空交给 pip 自己解析，但标签要如实写出用的是哪个，
    否则日志里会和「谁都没配」长得一模一样。
    """

    if is_package_index_offline():
        return [("离线", ["--no-index"])]
    user_index = str(os.environ.get("PIP_INDEX_URL") or "").strip()
    if user_index:
        return [(mask_url_credentials(f"PIP_INDEX_URL={user_index}"), [])]
    candidates = resolve_package_index_candidates()
    if not candidates:
        return [("PyPI 默认索引", [])]
    return [
        (mask_url_credentials(candidate), ["--index-url", candidate])
        for candidate in candidates
    ]


def _pip_install(
    python_exe: str,
    packages: list[str],
    *,
    cwd: str | None,
    env: dict[str, str],
    log: Callable[[str], None],
) -> tuple[bool, str]:
    """往 ``python_exe`` 里装包，返回 (是否成功, 最后一次失败原因)。

    与运行池的 ``_run_with_source_rotation`` 有一处有意的分歧：那边超时直接抛出、
    不换源，这里超时也接着试下一个候选。装不上的首要成因就是某个索引连不通，而
    连不通的典型表现正是超时，不换源等于白轮换。反过来，解释器自己起不来
    （``OSError``）与索引无关，立即停手，不必对着每个候选各失败一次。

    项目自带的 Python 常是 embeddable 发行版，没有 pip（M9A 就是：``python -m pip``
    报 ``No module named pip``）；遇到就换成 ``uv pip install --python <exe>`` 往同一个
    解释器里装，同一个索引候选重试一次。
    """

    last_detail = ""
    uv_exe: str | None = None
    for label, index_args in _pip_index_arg_candidates():
        while True:
            if uv_exe is None:
                command = [python_exe, "-m", "pip", "install", "--quiet"]
                tool = "pip install"
            else:
                # uv 不认 PIP_INDEX_URL，用户配了就显式带上；--no-config 免得读到
                # 用户目录里的 uv.toml / 项目 pyproject 的 uv 段
                uv_index_args = list(index_args)
                user_index = str(
                    env.get("PIP_INDEX_URL") or os.environ.get("PIP_INDEX_URL") or ""
                ).strip()
                if not uv_index_args and user_index:
                    uv_index_args = ["--index-url", user_index]
                command = [
                    uv_exe,
                    "pip",
                    "install",
                    "--python",
                    python_exe,
                    "--no-config",
                    "--quiet",
                    *uv_index_args,
                ]
                index_args = []
                tool = "uv pip install"
            try:
                result = subprocess.run(
                    [*command, *index_args, *packages],
                    capture_output=True,
                    timeout=PIP_INSTALL_PER_INDEX_TIMEOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                    env=env,
                )
                if result.returncode == 0:
                    log(f"[Python环境] {tool} 完成 ({label}): {', '.join(packages)}")
                    return True, ""
                last_detail = mask_url_credentials(
                    (result.stderr or result.stdout or "").strip()
                )
                if uv_exe is None and "No module named pip" in last_detail:
                    uv_exe = _find_uv_executable()
                    if uv_exe is None:
                        log(
                            "[Python环境] 解释器不带 pip（embeddable 发行版），"
                            "也找不到可用的 uv，无法安装"
                        )
                        return False, output_tail(last_detail, 300)
                    log(
                        "[Python环境] 解释器不带 pip（embeddable 发行版），改用 uv 安装"
                    )
                    continue
                log(
                    f"[Python环境] {tool} 未成功 ({label}): {output_tail(last_detail, 300)}"
                )
            except subprocess.TimeoutExpired:
                last_detail = f"{label} 超时 ({PIP_INSTALL_PER_INDEX_TIMEOUT}s)"
                log(
                    f"[Python环境] {tool} 超时 ({label}, {PIP_INSTALL_PER_INDEX_TIMEOUT}s)"
                )
            except OSError as exc:
                # 起不了子进程（venv 被删、python.exe 不在了）与索引无关，别再轮换。
                last_detail = mask_url_credentials(f"无法启动 {command[0]}: {exc}")
                log(
                    f"[Python环境] {tool} 无法启动 ({label}): {mask_url_credentials(exc)}"
                )
                return False, output_tail(last_detail, 300)
            except Exception as exc:
                last_detail = mask_url_credentials(f"{label}: {exc}")
                log(f"[Python环境] {tool} 异常 ({label}): {mask_url_credentials(exc)}")
            break
    return False, output_tail(last_detail, 300)


def _python_supports_venv(python: str) -> bool:
    """探测解释器是否带 venv/ensurepip 标准库。

    便携目录常见 embeddable 发行版（python3xx._pth），不带 venv 模块，
    直接 `-m venv` 会报 "No module named venv"，必须先探测再用作引导。
    """
    try:
        result = subprocess.run(
            [python, "-c", "import venv, ensurepip"],
            capture_output=True,
            timeout=VENV_PROBE_TIMEOUT,
            text=True,
            # 宿主 PYTHONHOME 会让解释器起不来、PYTHONWARNINGS=error 会让探测误判成「不可用」。
            env=strip_host_python_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _find_uv_executable() -> str | None:
    # 受管模式（AUTO-MAS-Runtime 监督后端）下没有便携 Python，监督器改为
    # 用 AUTO_MAS_UV_EXE 注入它已校验过的 uv 路径，也不会把这个 uv 加进
    # PATH——优先信它，找不到再退回便携路径与 PATH 查找。
    configured_uv = os.environ.get("AUTO_MAS_UV_EXE")
    if configured_uv:
        configured_path = Path(configured_uv)
        if configured_path.is_file():
            return str(configured_path.resolve())

    portable_uv = Path.cwd() / "environment" / "python" / "Scripts" / "uv.exe"
    if portable_uv.is_file():
        return str(portable_uv)

    # 用户从受管模式回退到旧链路时监督器不再注入变量，但 Runtime 早已把 uv 装在
    # runtime/tools/uv 下；和运行池共用同一份查找逻辑，免得两处各认一半。
    runtime_uv = runtime_managed_uv_executable()
    if runtime_uv is not None:
        return runtime_uv
    return shutil.which("uv")


def _venv_bootstrap_python() -> str | None:
    """返回第一个带 venv 模块的引导 Python；全部不可用时返回 None（改走 uv 兜底）。"""
    candidates: list[str] = []
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        candidates.append(str(portable_python))
    candidates.append(sys.executable)
    path_python = shutil.which("python")
    if path_python:
        candidates.append(path_python)
    for candidate in candidates:
        if _python_supports_venv(candidate):
            return candidate
    return None


def _safe_resolve_python(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except Exception:
        return path
