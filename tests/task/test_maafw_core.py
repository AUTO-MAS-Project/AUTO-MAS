"""MaaFW 核心最小回归：跨 MFW 各专项的公共测试。

M9A 等以 MFW 特调运行的专项，以及直接导入的各个 ``interface.json`` 项目，都跑在同一套
通用引擎上；这里守的是它们共用的那部分，不属于任何单个专项或单个功能的一次性测试。

只覆盖通用引擎 ``app/task/MaaFW/tools/core/``，不覆盖专项；只收缺一条就要命的：
守的东西一改坏，MFW 运行就成片失败。收录标准见 ``tests/AGENTS.md``「核心最小回归」；
功能与 bug 的边界测试照旧只在本地跑，不往这里放。改 ``tools/core/`` 前先跑：

    python -m pytest tests/task/test_maafw_core.py -q
"""

import ast
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from functools import cache
from importlib.metadata import packages_distributions
from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SOURCE_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 一、worker 导入闭包隔离
#
# worker 以 ``python -m app.task.MaaFW.tools.core.runner.worker`` 起在**运行池的
# 隔离 venv** 里：``app/task/MaaFW/tools/embedded/runner_task.py`` 只给它
# ``import_paths=[SOURCE_ROOT]``，不给宿主 venv 的 site-packages，所以那个解释器里
# 只有标准库、maafw binding 和 ``BASE_RUNTIME_PACKAGES`` 那几个包。
#
# 因此 worker 能触达的 ``app.*`` 模块必须全部待在 MaaFW 运行器自己的子树里，三方包
# 也只能是那几个。链路上任何一处 ``from app.utils import ...`` 之类的宿主导入，都会
# 因为包初始化连锁拉起 loguru 这样的宿主依赖，让 worker ``ModuleNotFoundError``。
# 宿主 venv 里跑测试永远是好的，只有隔离 venv 会撞上（v5.5.0-beta.4 全员 MFW 挂掉）。
#
# 函数体里的延迟导入一样算：worker 跑到那里同样会炸，只是晚一点。``if TYPE_CHECKING:``
# 块运行时不执行，不算；三方包的 ``try: import x / except ImportError`` 是可选依赖，
# 也不算。
# ---------------------------------------------------------------------------

WORKER_MODULE = "app.task.MaaFW.tools.core.runner.worker"

#: worker 允许触达的 ``app.*`` 范围：MaaFW 运行器与它的同层工具包。
ALLOWED_PREFIX = "app.task.MaaFW.tools.core."


@dataclass(frozen=True)
class _Import:
    target: str
    #: 包在 ``except ImportError`` 的 try 里，缺了也不会炸。
    optional: bool


def _module_file(module: str) -> Path | None:
    """把 ``app.x.y`` 解析成源码文件；不是本仓模块时返回 None。"""

    relative = Path(*module.split("."))
    for candidate in (
        SOURCE_ROOT / relative.with_suffix(".py"),
        SOURCE_ROOT / relative / "__init__.py",
    ):
        if candidate.is_file():
            return candidate
    return None


def _ancestors(module: str) -> list[str]:
    parts = module.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts))]


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _catches_import_error(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    names = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(
        isinstance(name, ast.Name) and name.id in {"ImportError", "ModuleNotFoundError"}
        for name in names
    )


class _ImportCollector(ast.NodeVisitor):
    """收集一个模块里所有会执行的 import（含函数体内的），跳过 TYPE_CHECKING 块。"""

    def __init__(self, module: str, is_package: bool) -> None:
        self.package = module if is_package else module.rsplit(".", 1)[0]
        self.found: list[_Import] = []
        self._optional_depth = 0

    def _add(self, target: str) -> None:
        self.found.append(_Import(target, self._optional_depth > 0))

    def visit_If(self, node: ast.If) -> None:
        if not _is_type_checking_guard(node):
            for statement in node.body:
                self.visit(statement)
        for statement in node.orelse:
            self.visit(statement)

    def visit_Try(self, node: ast.Try | ast.TryStar) -> None:
        optional = any(_catches_import_error(handler) for handler in node.handlers)
        self._optional_depth += optional
        for statement in node.body:
            self.visit(statement)
        self._optional_depth -= optional
        for handler in node.handlers:
            self.visit(handler)
        for statement in node.orelse + node.finalbody:
            self.visit(statement)

    visit_TryStar = visit_Try

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            base = self.package.split(".")
            base = base[: len(base) - node.level + 1]
            resolved = ".".join(base + ([node.module] if node.module else []))
        else:
            resolved = node.module or ""
        if not resolved:
            return
        self._add(resolved)
        # ``from pkg import mod`` 里的 mod 也可能是子模块。
        for alias in node.names:
            child = f"{resolved}.{alias.name}"
            if _module_file(child) is not None:
                self._add(child)


@cache
def _imports_of(module: str) -> tuple[_Import, ...]:
    path = _module_file(module)
    if path is None:
        return ()
    collector = _ImportCollector(module, path.name == "__init__.py")
    collector.visit(ast.parse(path.read_text(encoding="utf-8")))
    return tuple(collector.found)


def _worker_closure() -> dict[str, set[str]]:
    """返回 worker 导入闭包内的 ``app.*`` 模块，及各自的导入来源。"""

    # ``python -m`` 先逐级导入 worker 的祖先包，它们的 ``__init__`` 同样在闭包里。
    importers: dict[str, set[str]] = {
        name: set() for name in _ancestors(WORKER_MODULE) + [WORKER_MODULE]
    }
    pending = list(importers)
    while pending:
        module = pending.pop()
        for item in _imports_of(module):
            target = item.target
            if target != "app" and not target.startswith("app."):
                continue
            for name in _ancestors(target) + [target]:
                if name not in importers:
                    importers[name] = set()
                    pending.append(name)
                importers[name].add(module)
    return importers


def _is_allowed(module: str) -> bool:
    if module.startswith(ALLOWED_PREFIX):
        return True
    # ``app`` / ``app.task`` / ... 是 worker 自己的祖先包，``python -m`` 必然
    # 要导入它们；它们自身的越界导入仍会被闭包抓到。
    return ALLOWED_PREFIX.startswith(module + ".")


def _runner_venv_import_roots() -> set[str]:
    """运行池 venv 里装着的三方包的顶层模块名：maafw binding + BASE_RUNTIME_PACKAGES。"""

    from app.task.MaaFW.tools.core.runner.environment import BASE_RUNTIME_PACKAGES

    allowed = {
        canonicalize_name(Requirement(spec).name) for spec in BASE_RUNTIME_PACKAGES
    }
    allowed.add("maafw")
    return {
        root
        for root, distributions in packages_distributions().items()
        if any(canonicalize_name(name) in allowed for name in distributions)
    }


def test_worker_closure_stays_inside_runner_subtree() -> None:
    assert _module_file(WORKER_MODULE) is not None, "worker 模块不见了，先修路径"

    violations = sorted(
        (module, sorted(sources))
        for module, sources in _worker_closure().items()
        if not _is_allowed(module)
    )

    detail = "; ".join(
        f"{module} <- {', '.join(sources)}" for module, sources in violations
    )
    assert not violations, (
        "worker 会跑在运行池的隔离 venv 里，它的导入闭包不得越出 "
        f"{ALLOWED_PREFIX}*；越界的是：{detail}"
    )


def test_worker_closure_only_uses_runner_venv_packages() -> None:
    allowed_roots = _runner_venv_import_roots()
    assert {"maa", "pydantic"} <= allowed_roots, "没解析出运行池 venv 的包，守卫失效"

    violations: dict[str, set[str]] = {}
    for module in _worker_closure():
        path = _module_file(module)
        if path is None:
            continue
        for item in _imports_of(module):
            root = item.target.split(".", 1)[0]
            if (
                item.optional
                or root in {"app", "__future__"}
                or root in sys.stdlib_module_names
                or root in allowed_roots
                # worker 以脚本方式启动时按裸名导入同目录的兄弟模块
                or (path.parent / f"{root}.py").is_file()
            ):
                continue
            violations.setdefault(root, set()).add(module)

    detail = "; ".join(
        f"{root} <- {', '.join(sorted(sources))}"
        for root, sources in sorted(violations.items())
    )
    assert not violations, (
        "运行池 venv 只装了 maafw 与 BASE_RUNTIME_PACKAGES，worker 闭包里用到别的"
        f"三方包会直接 ModuleNotFoundError（真要用就先加进 BASE_RUNTIME_PACKAGES）：{detail}"
    )


# ---------------------------------------------------------------------------
# 二、宿主 ↔ worker 的进程边界
#
# 宿主把运行计划写成 job 文件交给 worker，worker 把结果以 JSON 发回来，两边各自
# ``model_validate``。任何一个方向序列化不回来，每一次 MFW 运行都直接失败；worker
# 按键名取值，宿主改了键名而 worker 还读旧的，拿到的是 None 而不是报错。
# ---------------------------------------------------------------------------


def _worker_payload_keys() -> set[str]:
    """worker 从 job 文件里读的顶层键：``payload["k"]`` 与 ``payload.get("k")``。"""

    path = _module_file(WORKER_MODULE)
    assert path is not None
    keys: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "payload"
            and isinstance(node.slice, ast.Constant)
        ):
            keys.add(node.slice.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "payload"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(node.args[0].value)
    return keys


def _sample_plan(project: Path):
    from app.task.MaaFW.tools.core.runner.models import (
        MaaFWResolvedPath,
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
        MaaFWSkippedTaskPlan,
        MaaFWTaskRunPlan,
    )

    resource_dir = MaaFWResolvedPath(
        raw="resource", resolved=str(project / "resource"), exists=True, isDir=True
    )
    return MaaFWRunPlan(
        path=str(project),
        projectName="M9A",
        projectLabel="重返未来：1999",
        controllerName="安卓端",
        controllerType="Adb",
        controllerDisplay={"display_short_side": 720},
        resourceName="官服",
        resource=MaaFWResourceBundlePlan(
            name="官服", paths=[resource_dir], hash="0123abcd"
        ),
        piEnv={"PI_CLIENT_LANGUAGE": "zh_cn"},
        tasks=[
            MaaFWTaskRunPlan(
                name="切换账号",
                entry="SwitchAccount",
                options={"账号": "主号"},
                pipelineOverride={"SwitchAccount": {"enabled": True}},
                nonDefaultOptions={"账号": "主号"},
                abortRoundMessage="切换账号失败",
            )
        ],
        skippedTasks=[MaaFWSkippedTaskPlan(name="活动", reason="未启用")],
        warnings=["快捷键未设置，已跳过"],
        i18n={"$award": "领取奖励"},
    )


def test_job_file_round_trips_to_worker(tmp_path: Path) -> None:
    from app.task.MaaFW.tools.core.runner.models import (
        MaaFWDeviceConfig,
        MaaFWRunnerJobPayload,
    )
    from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService

    service = MaaFWRunnerService()
    payload = service.create_job_payload(
        _sample_plan(tmp_path),
        MaaFWDeviceConfig(
            type="Adb",
            adbPath="C:/MuMu/shell/adb.exe",
            address="127.0.0.1:16384",
            screencapMethods=64,
            inputMethods=1,
            config={"extras": {"mumu": {"enable": True, "index": 0}}},
            adbReadyTimeout=120,
        ),
        failure_screenshot_dir=tmp_path / "history",
        failure_screenshot_prefix="12-00-00",
        task_start_not_before=1_700_000_000.5,
        run_deadline_at=1_700_003_600.5,
        task_time_limit_seconds=2700,
        task_time_limit_overrides={"切换账号": 600},
    )
    job_path = service.write_job_file(payload, tmp_path / "jobs")
    on_disk = json.loads(job_path.read_text(encoding="utf-8"))

    # worker 按这些键取值；宿主不写、或改了名，worker 拿到的就是 None。
    read_by_worker = _worker_payload_keys()
    assert {"plan", "deviceConfig", "ownerPid"} <= read_by_worker, (
        "没从 worker.py 里认出它读的键，守卫失效"
    )
    missing = read_by_worker - set(MaaFWRunnerJobPayload.model_fields)
    assert not missing, f"worker 读的键宿主不写：{sorted(missing)}"

    assert MaaFWRunnerJobPayload.model_validate(on_disk) == payload


def test_worker_result_survives_host_validation() -> None:
    from app.task.MaaFW.tools.core.runner.models import (
        MaaFWFailureScreenshot,
        MaaFWRunResult,
    )

    result = MaaFWRunResult(
        success=False,
        projectName="M9A",
        controllerName="安卓端",
        resourceName="官服",
        completedTasks=["领取奖励"],
        failedTask="切换账号",
        errorMessage="切换账号失败",
        failureScreenshots=[
            MaaFWFailureScreenshot(task="切换账号", path="C:/history/1.png")
        ],
        timedOut=True,
        signal="server_maintenance",
        signalNode="MaintenanceNotice",
    )
    # worker.py 发 {"type": "result", "data": model_dump(mode="json")}，宿主
    # runner_task 用 models.MaaFWRunResult.model_validate 收。
    wire = json.loads(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))

    assert MaaFWRunResult.model_validate(wire) == result


# ---------------------------------------------------------------------------
# 三、agent 运行环境
#
# MaaFW 的 AgentServer（agent 侧）与 AgentClient（runner 侧）之间有协议版本号，跨版本
# 直接拒绝握手，我们这边只表现为「AgentClient 连接超时」，每次运行都连不上。runner
# 加载的是项目自带的那份原生库，agent venv 里的 maafw binding 必须跟它同版本。很多
# 项目的 requirements.txt 写的是无版本约束的 ``MaaFw``，pip 会拉到当时的最新版；
# maafw 5.13.0（2026-09-07）把协议号从 7 抬到 8 时，这些项目的 agent 全部连不上。
# ---------------------------------------------------------------------------

# 照抄真实原生库里的排布：版本号是一条 NUL 结尾的 C 字符串，前后都是别的字符串。
# 取自 Maa_bbb v1.12.10 自带的 MaaFramework.dll。
_DLL_TEMPLATE = (
    b"\x00\x00\x00\x00latest_id\x00\x00\x00\x00%s\x00DoNothing\x00\x00\x00MaaAdbC"
)


def _project_with_bundled_maafw(
    tmp_path: Path, requirements: list[str], version: str = "v5.12.3"
) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text(
        "\n".join(requirements) + "\n", encoding="utf-8"
    )
    runtime_dir = project / "maafw"
    runtime_dir.mkdir()
    (runtime_dir / "MaaFramework.dll").write_bytes(
        _DLL_TEMPLATE % version.encode("ascii")
    )
    return project


@pytest.mark.parametrize(
    ("declared", "pinned"),
    [
        (["json-with-comments", "MaaFw"], ["json-with-comments", "maafw==5.12.3"]),
        # 声明与自带库对不上时以自带库为准——runner 加载的是自带的那份。
        (["maafw==5.13.0"], ["maafw==5.12.3"]),
    ],
)
def test_agent_maafw_is_pinned_to_bundled_runtime(
    tmp_path: Path, declared: list[str], pinned: list[str]
) -> None:
    from app.task.MaaFW.tools.core.agent_env.env import (
        _load_project_agent_requirements,
    )
    from app.task.MaaFW.tools.core.runner.environment import (
        pin_agent_maafw_requirement,
    )

    project = _project_with_bundled_maafw(tmp_path, declared)

    assert pin_agent_maafw_requirement(project, declared) == pinned
    # agent_env 的 loader 是准备 agent venv 的唯一入口，钉版必须走到这里。
    loaded = _load_project_agent_requirements(project)
    assert [item for item in loaded if item.lower().startswith("maafw")] == [
        "maafw==5.12.3"
    ]


def test_agent_manifest_carries_the_pin(tmp_path: Path) -> None:
    """agent venv 的复用判据是 ``requirementsHash``；钉版不进哈希，已经装错的 venv
    会因为「依赖清单没变」被永远复用，修了也送不到用户那里。"""

    from app.task.MaaFW.tools.core.agent_env.env import build_agent_env_manifest

    declared = ["json-with-comments", "MaaFw"]
    project = _project_with_bundled_maafw(tmp_path, declared)

    manifest = build_agent_env_manifest(project)

    assert "maafw==5.12.3" in manifest["requirements"]
    stale_payload = json.dumps(declared, ensure_ascii=False, separators=(",", ":"))
    stale_hash = hashlib.sha256(stale_payload.encode("utf-8")).hexdigest()
    assert manifest["requirementsHash"] != stale_hash


def _fake_venv(root: Path, home: Path) -> Path:
    from app.task.MaaFW.tools.core.agent_env.planner import venv_python_exe

    venv_path = root / "maafw_venv_fake"
    python = venv_python_exe(venv_path)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    (venv_path / "pyvenv.cfg").write_text(
        f"home = {home}\nversion_info = 3.12.10\n", encoding="utf-8"
    )
    return venv_path


def test_agent_venv_is_invalid_once_base_interpreter_is_gone(tmp_path: Path) -> None:
    """Runtime 修复或重建后端 venv 后，用它建的 agent venv 的 ``pyvenv.cfg`` 里
    ``home`` 指向已删除的目录；Windows 上 venv 的 python.exe 只是重定向存根，home
    没了就起不来。这时必须判失效重建，否则所有 Python agent 项目都起不来——源码树
    开发不经过 Runtime，看不到。"""

    from app.task.MaaFW.tools.core.agent_env.env import _is_valid_venv_path

    gone = _fake_venv(tmp_path / "a", tmp_path / "deleted-backend-venv")
    assert not _is_valid_venv_path(gone)

    home = tmp_path / "backend-venv"
    home.mkdir()
    (home / ("python.exe" if os.name == "nt" else "python")).write_bytes(b"")
    assert _is_valid_venv_path(_fake_venv(tmp_path / "b", home))


# 项目里并存两份原生库（导入的目录被外壳原地升级过，``maafw/`` 与 ``runtimes/<rid>/native``
# 各一份、版本不同）时，agent 若加载了 runner 之外的那份，两边协议版本对不上，每次都等满连接
# 超时（09-30 M9A v4.11.0：``maafw/`` 5.9.2、``runtimes/win-x64/native`` 5.14.0）。

_OLD, _NEW = "5.9.2", "5.14.0"
_MAAFW_DIR = Path("maafw")
_NATIVE_DIR = Path("runtimes") / "win-x64" / "native"


@pytest.fixture
def no_pool_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MAAFW_BINARY_PATH", "AUTO_MAS_MAAFW_NATIVE_DIR"):
        monkeypatch.delenv(key, raising=False)


def _native(directory: Path, version: str) -> None:
    """合成原生库：版本串按 MaaFramework 内嵌的 ``v<版本>`` 形式写进 DLL 字节。"""

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "MaaFramework.dll").write_bytes(
        b"\0MaaFramework v" + version.encode() + b"\0"
    )
    (directory / "MaaAgentServer.dll").write_bytes(b"\0")


def _mixed_project(tmp_path: Path, natives: dict[Path, str]) -> Path:
    """自带解释器里有 maa 包、没有 maa/bin（M9A v4.10+ 的发行形态）。"""

    project = tmp_path / "proj"
    maa = project / "python" / "Lib" / "site-packages" / "maa"
    maa.mkdir(parents=True)
    (maa / "__init__.py").write_text("", encoding="utf-8")
    (project / "python" / "Scripts").mkdir()
    for relative, version in natives.items():
        _native(project / relative, version)
    return project


def _agent_plan(project: Path, kind: str):
    from app.task.MaaFW.tools.core.agent_env.models import MaaFWAgentCommandPlan

    if kind == "project_python":
        exe = project / "python" / "python.exe"
        command = [str(exe), "-u", "agent/main.py", "<socket_id>"]
    else:
        exe = project / "agent" / "go-service.exe"
        command = [str(exe), "<socket_id>"]
    return MaaFWAgentCommandPlan(
        childExec=exe.relative_to(project).as_posix(),
        executable=str(exe),
        runtimeKind=kind,
        command=command,
        cwd=str(project),
    )


def _fake_runner(project: Path, *agents) -> SimpleNamespace:
    return SimpleNamespace(
        plan=SimpleNamespace(path=str(project), piEnv={}, agents=list(agents)),
        send_log=lambda message: None,
    )


@pytest.mark.usefixtures("no_pool_runtime")
@pytest.mark.parametrize(
    ("natives", "chosen"),
    [
        ({_MAAFW_DIR: _OLD, _NATIVE_DIR: _NEW}, _NATIVE_DIR),
        ({_MAAFW_DIR: _NEW, _NATIVE_DIR: _OLD}, _MAAFW_DIR),
    ],
    ids=["maafw-old", "runtimes-old"],
)
def test_python_agent_uses_runner_runtime(
    tmp_path: Path, natives: dict[Path, str], chosen: Path
) -> None:
    """两份并存时 runner 取版本高的那份，agent 的 MAAFW_BINARY_PATH 与 PATH 上第一个项目
    原生库目录都必须是它。"""

    from app.task.MaaFW.tools.core.runner.runner import (
        MaaFWRunner,
        runner_maafw_runtime_path,
    )

    project = _mixed_project(tmp_path, natives)
    runtime = runner_maafw_runtime_path(project)
    assert runtime == project / chosen

    env = MaaFWRunner._build_agent_env(
        _fake_runner(project), _agent_plan(project, "project_python")
    )
    assert env["MAAFW_BINARY_PATH"] == str(runtime)
    python_dir = os.path.normcase(str(project / "python"))
    project_dirs = [
        item
        for item in env["PATH"].split(os.pathsep)
        if os.path.normcase(item).startswith(os.path.normcase(str(project)))
        and not os.path.normcase(item).startswith(python_dir)
    ]
    assert project_dirs[0] == str(runtime)


@pytest.mark.usefixtures("no_pool_runtime")
def test_native_agent_version_mismatch_fails_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """原生 agent 固定从 maafw/ 加载，runner 选了另一份且版本不同时，必须在建 AgentClient、
    起子进程之前就抛错，而不是每次起一个注定连不上的 agent、等满连接超时。"""

    from app.task.MaaFW.tools.core.runner import runner as runner_module
    from app.task.MaaFW.tools.core.runner.runner import MaaFWRunner

    project = _mixed_project(tmp_path, {_MAAFW_DIR: _OLD, _NATIVE_DIR: _NEW})
    fake = _fake_runner(project, _agent_plan(project, "project_binary"))
    fake._load_embedded_agents = lambda: None
    fake.prepare_agent_python_envs = lambda: None
    fake._run_agent_identifier = lambda identifier, child_exec: None
    fake._check_native_agent_runtime = lambda plan: (
        MaaFWRunner._check_native_agent_runtime(fake, plan)
    )

    def _must_not_spawn(*args, **kwargs):
        raise AssertionError("版本不一致时不该走到启动 agent")

    fake._create_agent_client = _must_not_spawn
    monkeypatch.setattr(runner_module.subprocess, "Popen", _must_not_spawn)

    with pytest.raises(RuntimeError) as info:
        MaaFWRunner._start_agents(fake)
    assert _OLD in str(info.value)
    assert _NEW in str(info.value)


@pytest.mark.usefixtures("no_pool_runtime")
def test_native_agent_on_plain_layout_not_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """项目只自带 maafw/ 一份原生库的常规布局，宿主同时给了运行池里另一版本的官方库，
    runner 用的仍是项目那份，核对必须放行；误报就是所有原生 agent 项目都启动不了。"""

    from app.task.MaaFW.tools.core.runner.runner import MaaFWRunner

    project = _mixed_project(tmp_path, {_MAAFW_DIR: _NEW})
    pool = tmp_path / "pool" / "native"
    _native(pool, _OLD)
    monkeypatch.setenv("AUTO_MAS_MAAFW_NATIVE_DIR", str(pool))

    plan = _agent_plan(project, "project_binary")
    MaaFWRunner._check_native_agent_runtime(_fake_runner(project, plan), plan)
