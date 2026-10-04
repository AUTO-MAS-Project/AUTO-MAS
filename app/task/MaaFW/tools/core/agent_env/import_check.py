"""Python agent 的导入静态检查：新版本登记前拦下「agent 一启动就 ModuleNotFoundError」的包。

v5.6.0 的 MaaFgo v2.0.01 → v2.0.03：投影漏装了 ``agent/battle/runtime/*.py``，而预检只验证了
解释器能 ``import maa``，缺模块的版本被登记、切换，之后每次运行 agent 都报
``No module named 'battle.runtime'``。这里补一道检查，规则（宁可漏报，不可误拒）：

- **拒绝**：启动时必然执行的导入（入口脚本及其顶层导入连带的项目文件里、不在函数 / if /
  吞 ImportError 的 try 里）引用了项目自己的包（落在项目代码目录里，不在解释器目录里），
  而这个包下的子模块在所有候选位置都找不到，且沿途包的 ``__init__`` 没有改 ``__path__``
  之类的动态手脚。
- **只提示**：第三方包或标准库找不到（项目自带 Python 的依赖可能由项目运行时自行安装；
  隔离 venv 在检查前已按 requirements 装好）、项目模块缺失但出现在非启动路径、条件导入、
  函数内导入、``try/except ImportError`` 与 ``if TYPE_CHECKING`` 里的导入。
- **不下结论**：不是 Python agent、入口不是 ``.py``（``-m`` 形式）、解释器起不来、超时、
  目录过大——都只记一行日志。

不执行项目代码：探针（``_import_probe.py``）在项目解释器里只做 ``ast`` 解析与 finder 查找，
见其模块说明。环境与真实 agent 子进程一致（``runner._build_agent_env``：剔除宿主 Python
变量、``PYTHONUTF8``、pyc 前缀），另加 ``-B`` 不写字节码。三处有意的差别：cwd 是空的临时
目录而不是项目根（见 :func:`check_agent_script_imports`）；``PYTHONPATH``（项目根）不走
环境变量、由探针启动后插回 sys.path 的同一位置——走环境变量的话解释器启动时会从项目根
import ``sitecustomize``；隔离 venv 的兼容 shim 目录不放（它只 patch ``maa``，与找模块
无关）。解释器自己 site-packages 里的 ``.pth`` 仍照常处理：那是解释器的一部分，现有的
健康检查同样会跑。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..runtime_pool._shared import output_tail
from ..runtime_pool.host_environment import (
    set_project_pycache_prefix,
    strip_host_python_environment,
)
from .models import MaaFWAgentCommandPlan
from .planner import MaaFWAgentEnvError

#: 预检失败条目里的 ``kind``：新版本缺 agent 模块（备忘里仍按 other 记，不自动重试）
KIND_AGENT_MODULE_MISSING = "agent_module_missing"
IMPORT_CHECK_TIMEOUT_SECONDS = 60
LOG_PREFIX = "[Agent 导入检查] "
PYTHON_RUNTIME_KINDS = frozenset({"project_python", "isolated_venv"})
_PROBE_PATH = Path(__file__).with_name("_import_probe.py")
_MAX_LISTED = 6


class MaaFWAgentImportMissingError(MaaFWAgentEnvError):
    """新版本的 agent 在启动时就会 import 一个项目里不存在的模块。"""

    def __init__(self, message: str, findings: list[AgentImportFinding]) -> None:
        super().__init__(message)
        self.findings = findings


@dataclass(frozen=True)
class AgentImportFinding:
    module: str
    file: str
    line: int

    def where(self) -> str:
        return f"{self.file} 第 {self.line} 行引用"


@dataclass
class AgentImportReport:
    entry: str
    checked: bool = False
    skipped_reason: str | None = None
    missing: list[AgentImportFinding] = field(default_factory=list)
    soft_missing: list[AgentImportFinding] = field(default_factory=list)
    external_missing: list[AgentImportFinding] = field(default_factory=list)
    unparsable: list[str] = field(default_factory=list)
    files: int = 0
    startup_files: int = 0
    elapsed: float = 0.0


def resolve_agent_entry(
    project_path: Path, plan: MaaFWAgentCommandPlan
) -> tuple[str, Path] | str:
    """plan → ``(解释器, 入口脚本)``；不适用时返回不检查的原因。"""

    if (plan.runtimeKind or "external") not in PYTHON_RUNTIME_KINDS:
        return f"{plan.childExec} 不是 Python agent"
    python_exe = plan.command[0] if plan.command else plan.executable
    if not python_exe or not Path(python_exe).is_file():
        return f"解释器不存在：{python_exe}"
    args = [str(arg) for arg in plan.childArgs]
    if "-m" in args or "-c" in args:
        return "入口不是脚本文件（-m / -c 形式）"
    cwd = Path(plan.cwd or project_path)
    for arg in args:
        if arg.lower().endswith((".py", ".pyw")):
            entry = Path(arg)
            if not entry.is_absolute():
                entry = cwd / entry
            entry = entry.resolve()
            if not entry.is_file():
                return f"入口脚本不存在：{arg}"
            return python_exe, entry
    return "没有 .py 入口"


def _probe_env(project_path: Path) -> dict[str, str]:
    # PYTHONPATH（agent 子进程里是项目根）不放进环境：解释器启动时会从它 import
    # sitecustomize，那就执行了项目代码。探针启动后按同一位置自己补进 sys.path。
    env = strip_host_python_environment()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    set_project_pycache_prefix(env, project_path)
    return env


def _findings(items: Any) -> list[AgentImportFinding]:
    result: list[AgentImportFinding] = []
    for item in items or []:
        try:
            result.append(
                AgentImportFinding(
                    module=str(item["module"]),
                    file=str(item["file"]),
                    line=int(item["line"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result


def check_agent_script_imports(
    project_path: str | Path,
    python_exe: str | Path,
    entry: str | Path,
    *,
    timeout: float = IMPORT_CHECK_TIMEOUT_SECONDS,
) -> AgentImportReport:
    """用 ``python_exe`` 检查 ``entry`` 启动时的导入。任何意外都只返回 ``checked=False``。

    子进程的 cwd 是空的临时目录，不是项目根：``-c`` 把 cwd（``''``）放在 sys.path 最前，
    探针自己的 ``import json`` 等就会先在 cwd 里找，项目根下的 ``json.py`` 会被执行。
    真实 agent 以 ``python <入口>.py`` 启动，cwd 不在它的 sys.path 上（在的是入口目录，
    探针自己换上），所以判定不受影响。
    """

    project = Path(project_path).resolve()
    entry_path = Path(entry).resolve()
    report = AgentImportReport(entry=_relative(entry_path, project))
    started = time.perf_counter()
    try:
        source = _PROBE_PATH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="mas-agent-import-") as neutral_cwd:
            result = subprocess.run(
                [str(python_exe), "-B", "-c", source],
                input=json.dumps(
                    {
                        "project": str(project),
                        "entry": str(entry_path),
                        "pythonpath": str(project),
                    }
                ),
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=neutral_cwd,
                env=_probe_env(project),
            )
    except subprocess.TimeoutExpired:
        report.skipped_reason = f"超时（{timeout:g}s）"
        return report
    except OSError as exc:
        report.skipped_reason = f"解释器起不来：{exc}"
        return report
    finally:
        report.elapsed = time.perf_counter() - started

    payload: dict[str, Any] | None = None
    for line in reversed((result.stdout or "").splitlines()):
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = None
            break
    if not isinstance(payload, dict):
        detail = (result.stderr or result.stdout or "").strip()
        report.skipped_reason = f"检查进程没有给出结果（exit={result.returncode}）" + (
            f"：{output_tail(detail, 200)}" if detail else ""
        )
        return report
    if not payload.get("checked"):
        report.skipped_reason = str(payload.get("reason") or "未知原因")
        return report
    report.checked = True
    report.missing = _findings(payload.get("missing"))
    report.soft_missing = _findings(payload.get("softMissing"))
    report.external_missing = _findings(payload.get("externalMissing"))
    report.unparsable = [str(item) for item in payload.get("unparsable") or []]
    report.files = int(payload.get("files") or 0)
    report.startup_files = int(payload.get("startupFiles") or 0)
    return report


def check_agent_plan_imports(
    project_path: str | Path,
    plans: Iterable[MaaFWAgentCommandPlan],
    *,
    timeout: float = IMPORT_CHECK_TIMEOUT_SECONDS,
) -> list[AgentImportReport]:
    """逐个 Python agent 检查；同一个入口只查一次。"""

    project = Path(project_path).resolve()
    reports: list[AgentImportReport] = []
    seen: set[tuple[str, str]] = set()
    for plan in plans:
        resolved = resolve_agent_entry(project, plan)
        if isinstance(resolved, str):
            reports.append(
                AgentImportReport(entry=plan.childExec, skipped_reason=resolved)
            )
            continue
        python_exe, entry = resolved
        key = (os.path.normcase(str(python_exe)), os.path.normcase(str(entry)))
        if key in seen:
            continue
        seen.add(key)
        reports.append(
            check_agent_script_imports(project, python_exe, entry, timeout=timeout)
        )
    return reports


def describe_missing_agent_modules(
    findings: list[AgentImportFinding], previous_version: str | None
) -> str:
    """拒绝新版本时给用户看的一句话（任务日志、通知、手动更新的报错第一行）。"""

    first = findings[0]
    more = f"等 {len(findings)} 个模块" if len(findings) > 1 else ""
    previous = str(previous_version or "").strip() or "当前版本"
    return (
        f"新版本缺少 agent 模块 {first.module}（{first.where()}）{more}，"
        f"已放弃更新，继续使用 {previous}"
    )


def _join_modules(findings: list[AgentImportFinding]) -> str:
    names = list(dict.fromkeys(item.module for item in findings))
    text = "、".join(names[:_MAX_LISTED])
    if len(names) > _MAX_LISTED:
        text += f" 等 {len(names)} 个"
    return text


def log_agent_import_reports(
    reports: list[AgentImportReport],
    log: Callable[[str], None],
    *,
    blocking: bool,
) -> list[AgentImportFinding]:
    """把检查结论写进日志，返回会让 agent 起不来的缺失模块（调用方决定拒不拒）。

    ``blocking`` 只影响缺失模块那行的措辞：预检里调用方随后拒绝新版本，
    导入 / 准备环境时只提示。
    """

    missing: list[AgentImportFinding] = []
    for report in reports:
        if not report.checked:
            if (
                report.skipped_reason
                and "不是 Python agent" not in report.skipped_reason
            ):
                log(f"{LOG_PREFIX}跳过 {report.entry}：{report.skipped_reason}")
            continue
        for item in report.missing:
            if blocking:
                log(f"{LOG_PREFIX}缺少项目模块 {item.module}（{item.where()}）")
            else:
                log(
                    f"{LOG_PREFIX}缺少项目模块 {item.module}（{item.where()}），"
                    "agent 启动时会报 ModuleNotFoundError"
                )
        missing.extend(report.missing)
        if report.external_missing:
            log(
                f"{LOG_PREFIX}当前环境里找不到 {_join_modules(report.external_missing)}"
                "（第三方依赖可能由项目运行时自行安装），仅提示"
            )
        if report.soft_missing:
            log(
                f"{LOG_PREFIX}非启动路径引用的项目模块不存在："
                f"{_join_modules(report.soft_missing)}，仅提示"
            )
        if not report.missing:
            log(
                f"{LOG_PREFIX}{report.entry} 通过（{report.files} 个文件，"
                f"{report.elapsed:.1f}s）"
            )
    return missing


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


__all__ = [
    "IMPORT_CHECK_TIMEOUT_SECONDS",
    "KIND_AGENT_MODULE_MISSING",
    "AgentImportFinding",
    "AgentImportReport",
    "MaaFWAgentImportMissingError",
    "check_agent_plan_imports",
    "check_agent_script_imports",
    "describe_missing_agent_modules",
    "log_agent_import_reports",
    "resolve_agent_entry",
]
