"""MaaFW worker 进程的导入闭包隔离守卫。

worker 以 ``python -m app.task.MaaFW.tools.core.runner.worker`` 起在**运行池的
隔离 venv** 里：``app/task/MaaFW/tools/embedded/runner_task.py`` 只给它
``import_paths=[SOURCE_ROOT]``，不给宿主 venv 的 site-packages，所以那个解释器里
只有标准库、maafw binding 和 ``BASE_RUNTIME_PACKAGES`` 那几个包。

因此 worker 能触达的 ``app.*`` 模块必须全部待在 MaaFW 运行器自己的子树里。
链路上任何一处 ``from app.utils import ...`` 之类的宿主导入，都会因为包初始化
连锁拉起 loguru 这样的宿主依赖，让 worker 一启动就 ``ModuleNotFoundError``。
这类破坏还特别难发现：源码树跑测试永远是好的，只有装了包的用户会撞上
（v5.5.0-beta.4 全员 MFW 挂掉就是这样）。

守卫只看**模块级** import——决定 ``python -m`` 能不能起来的就是它们。
``if TYPE_CHECKING:`` 块运行时不执行，不算。它管不到第三方依赖有没有装（那要真起
一个隔离 venv 才知道），但越界的宿主导入一定先在这里露头。
"""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]

WORKER_MODULE = "app.task.MaaFW.tools.core.runner.worker"

#: worker 允许触达的 ``app.*`` 范围：MaaFW 运行器与它的同层工具包。
ALLOWED_PREFIX = "app.task.MaaFW.tools.core."


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


def _runtime_statements(statements: list[ast.stmt]) -> list[ast.stmt]:
    """展开模块级 ``if`` / ``try`` 里会在导入期执行的语句，跳过 TYPE_CHECKING 块。"""

    result: list[ast.stmt] = []
    for statement in statements:
        if isinstance(statement, ast.If):
            if not _is_type_checking_guard(statement):
                result.extend(_runtime_statements(statement.body))
            result.extend(_runtime_statements(statement.orelse))
        elif isinstance(statement, (ast.Try, ast.TryStar)):
            result.extend(_runtime_statements(statement.body))
            for handler in statement.handlers:
                result.extend(_runtime_statements(handler.body))
            result.extend(_runtime_statements(statement.orelse))
            result.extend(_runtime_statements(statement.finalbody))
        else:
            result.append(statement)
    return result


def _module_level_imports(path: Path, module: str) -> set[str]:
    """收集模块级 import 的目标模块名，含 ``if`` / ``try`` 包着的那些。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rsplit(".", 1)[0]
    targets: set[str] = set()
    for node in _runtime_statements(tree.body):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                resolved = ".".join(base + ([node.module] if node.module else []))
            else:
                resolved = node.module or ""
            if not resolved:
                continue
            targets.add(resolved)
            # ``from pkg import mod`` 里的 mod 也可能是子模块。
            for alias in node.names:
                child = f"{resolved}.{alias.name}"
                if _module_file(child) is not None:
                    targets.add(child)
    return targets


def _import_closure() -> dict[str, set[str]]:
    """返回 worker 模块级导入闭包内的 ``app.*`` 模块，及各自的导入来源。"""

    # ``python -m`` 先逐级导入 worker 的祖先包，它们的 ``__init__`` 同样在闭包里。
    importers: dict[str, set[str]] = {
        name: set() for name in _ancestors(WORKER_MODULE) + [WORKER_MODULE]
    }
    pending = list(importers)
    while pending:
        module = pending.pop()
        path = _module_file(module)
        if path is None:
            continue
        for target in sorted(_module_level_imports(path, module)):
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


def test_worker_import_closure_stays_inside_runner_subtree() -> None:
    assert _module_file(WORKER_MODULE) is not None, "worker 模块不见了，先修路径"

    importers = _import_closure()
    violations = sorted(
        (module, sorted(sources))
        for module, sources in importers.items()
        if not _is_allowed(module)
    )

    detail = "; ".join(
        f"{module} <- {', '.join(sources)}" for module, sources in violations
    )
    assert not violations, (
        "worker 会跑在运行池的隔离 venv 里，它的导入闭包不得越出 "
        f"{ALLOWED_PREFIX}*；越界的是：{detail}"
    )
