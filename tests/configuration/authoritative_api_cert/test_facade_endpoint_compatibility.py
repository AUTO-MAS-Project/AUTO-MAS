"""Facade endpoint 兼容性测试。

验证每个 API endpoint 使用的 Config 方法在 facade 中是否存在。
"""
import ast
import json
import sys
from pathlib import Path

import pytest

WORKTREE = Path(__file__).resolve().parents[3]
if str(WORKTREE) not in sys.path:
    sys.path.insert(0, str(WORKTREE))


def _find_endpoint_matrix() -> Path | None:
    """Locate the migrated certification artifact without pinning a drive layout."""

    relative_path = (
        Path("_alpha_build")
        / "a1"
        / "deepseek-authoritative-api-cert-20260723"
        / "api_endpoint_matrix.json"
    )
    for root in (WORKTREE, *WORKTREE.parents):
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return None


ENDPOINT_MATRIX_PATH = _find_endpoint_matrix()


def _load_matrix():
    if ENDPOINT_MATRIX_PATH is not None:
        with open(ENDPOINT_MATRIX_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _build_endpoint_matrix()


_ROUTER_NAMES = ("plan", "queue", "tools", "scripts", "info", "history")
_HTTP_METHODS = {
    "delete": "DELETE",
    "get": "GET",
    "patch": "PATCH",
    "post": "POST",
    "put": "PUT",
}


def _route_entries(function: ast.AsyncFunctionDef | ast.FunctionDef):
    """Yield current FastAPI route metadata from one endpoint function."""

    for decorator in function.decorator_list:
        if not (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "router"
        ):
            continue
        decorator_name = decorator.func.attr.lower()
        if decorator_name not in {*_HTTP_METHODS, "api_route"}:
            continue

        path = ""
        if decorator.args:
            value = decorator.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                path = value.value

        methods = [_HTTP_METHODS[decorator_name]] if decorator_name in _HTTP_METHODS else []
        if decorator_name == "api_route":
            for keyword in decorator.keywords:
                if keyword.arg != "methods" or not isinstance(
                    keyword.value,
                    (ast.List, ast.Tuple),
                ):
                    continue
                methods = [
                    str(item.value).upper()
                    for item in keyword.value.elts
                    if isinstance(item, ast.Constant)
                    and isinstance(item.value, str)
                ]

        for method in methods:
            yield {"method": method, "path": path}


def _direct_config_calls(function: ast.AsyncFunctionDef | ast.FunctionDef) -> list[str]:
    """Collect public direct ``Config.method(...)`` facade calls."""

    calls = {
        f"Config.{node.func.attr}("
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "Config"
    }
    return sorted(calls)


def _build_endpoint_matrix() -> dict[str, object]:
    """Build a reproducible matrix from the current API source tree."""

    routers: dict[str, dict[str, list[dict[str, object]]]] = {}
    for router_name in _ROUTER_NAMES:
        source_path = WORKTREE / "app" / "api" / f"{router_name}.py"
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"),
            filename=str(source_path),
        )
        endpoints: list[dict[str, object]] = []
        for node in tree.body:
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            config_calls = _direct_config_calls(node)
            for route in _route_entries(node):
                endpoints.append({**route, "config_calls": config_calls})
        routers[router_name] = {"endpoints": endpoints}
    return {"routers": routers}


_DEFERRED_NON_FACADE_MEMBERS = {"_game_sign_result_data"}


def _facade_method_name(call: str) -> str | None:
    """Return a public Config facade call, excluding documented internals.

    The legacy manual GameSign action reads an in-memory result cache rather
    than invoking a Config method.  It is explicitly fail-closed in
    authoritative mode until the native GameSign port lands, so including the
    cache member in facade method coverage would be a false requirement.
    """

    method_name = call.split("(")[0].split(".")[-1].strip()
    if method_name in _DEFERRED_NON_FACADE_MEMBERS:
        return None
    return method_name


class TestFacadeEndpointCoverage:
    """验证每个 API endpoint 的 Config 调用在 facade 中是否有对应。"""

    @pytest.fixture(scope="class")
    def matrix(self):
        return _load_matrix()

    @pytest.fixture(scope="class")
    def facade_methods(self):
        from app.core.native_config import NativeConfigFacade
        methods = [m for m in dir(NativeConfigFacade) if not m.startswith("_")]
        return set(methods)

    def test_plan_endpoints_fully_covered(self, matrix, facade_methods):
        """plan API 的所有 Config 调用应在 facade 中。"""
        plan_router = matrix["routers"]["plan"]
        for ep in plan_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                assert method_name in facade_methods, (
                    f"plan endpoint {ep['method']} {ep['path']} "
                    f"使用了 {method_name}，但不在 facade 中"
                )

    def test_queue_endpoints_fully_covered(self, matrix, facade_methods):
        """queue API 的所有 Config 调用应在 facade 中。"""
        queue_router = matrix["routers"]["queue"]
        for ep in queue_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                assert method_name in facade_methods, (
                    f"queue endpoint {ep['method']} {ep['path']} "
                    f"使用了 {method_name}，但不在 facade 中"
                )

    def test_tools_endpoints_fully_covered(self, matrix, facade_methods):
        """tools API 的所有 Config 调用应在 facade 中。"""
        tools_router = matrix["routers"]["tools"]
        for ep in tools_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                assert method_name in facade_methods, (
                    f"tools endpoint {ep['method']} {ep['path']} "
                    f"使用了 {method_name}，但不在 facade 中"
                )

    def test_scripts_endpoints_list_missing(self, matrix, facade_methods):
        """scripts API 的缺失方法应被明确列出。"""
        scripts_router = matrix["routers"]["scripts"]
        missing = []
        for ep in scripts_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                if method_name not in facade_methods:
                    missing.append(method_name)
        # 预期缺失但不作为测试失败——仅记录
        print(f"\nscripts API 缺失的方法: {sorted(set(missing))}")

    def test_info_endpoints_list_missing(self, matrix, facade_methods):
        """info API 的缺失方法应被明确列出。"""
        info_router = matrix["routers"]["info"]
        missing = []
        for ep in info_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                if method_name not in facade_methods:
                    missing.append(method_name)
        print(f"\ninfo API 缺失的方法: {sorted(set(missing))}")

    def test_history_endpoints_list_missing(self, matrix, facade_methods):
        """history API 的缺失方法应被明确列出。"""
        history_router = matrix["routers"]["history"]
        missing = []
        for ep in history_router["endpoints"]:
            for call in ep.get("config_calls", []):
                method_name = _facade_method_name(call)
                if method_name is None:
                    continue
                if method_name not in facade_methods:
                    missing.append(method_name)
        print(f"\nhistory API 缺失的方法: {sorted(set(missing))}")

    def test_facade_coverage_statistics(self, matrix, facade_methods):
        """计算 facade 覆盖率统计。"""
        total_calls = 0
        covered_calls = 0
        for router_name, router_data in matrix["routers"].items():
            for ep in router_data["endpoints"]:
                for call in ep.get("config_calls", []):
                    method_name = _facade_method_name(call)
                    if method_name is None:
                        continue
                    total_calls += 1
                    if method_name in facade_methods:
                        covered_calls += 1

        coverage = (covered_calls / total_calls * 100) if total_calls > 0 else 0
        print(f"\nFacade 覆盖率: {covered_calls}/{total_calls} = {coverage:.1f}%")
        # 预期覆盖率 > 60%（plan/emulator/queue/tools/setting 已完全覆盖）
        assert coverage > 60, f"Facade 覆盖率 {coverage:.1f}% 低于预期 60%"


class TestPluginHostConfigDependency:
    """验证插件宿主对 Config 的依赖点。"""

    PLUGIN_MODULES_WITH_CONFIG_DEP = [
        "app.plugins.config_store",
        "app.plugins.manager",
        "app.plugins.emulator_compat",
        "app.plugins.script_adapter",
    ]

    PLUGIN_MODULES_WITHOUT_CONFIG_DEP = [
        "app.plugins.loader",
        "app.plugins.context",
        "app.plugins.server",
        "app.plugins.service_registry",
        "app.plugins.event_bus",
        "app.plugins.event",
        "app.plugins.event_contract",
        "app.plugins.event_factory",
        "app.plugins.lifecycle",
        "app.plugins.lifecycle_hooks",
        "app.plugins.schema",
        "app.plugins.schema_utils",
        "app.plugins.decorators",
        "app.plugins.fields",
        "app.plugins.cache_store",
        "app.plugins.uv_backend",
        "app.plugins.pypi_site",
        "app.plugins.market_channel",
        "app.plugins.service_spec",
        "app.plugins.log",
        "app.plugins.log_pipeline",
        "app.plugins.realtime",
        "app.plugins.runtime_api",
        "app.plugins.market",
        "app.plugins.dev_hmr",
        "app.plugins.frontend_extensions",
        "app.plugins.system",
    ]

    @pytest.mark.parametrize("module_name", PLUGIN_MODULES_WITH_CONFIG_DEP)
    def test_module_has_config_dependency(self, module_name):
        """验证这些模块确实依赖 Config（已知阻断点）。"""
        import ast
        parts = module_name.split(".")
        module_path = WORKTREE.joinpath(*parts).with_suffix(".py")
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        has_config_import = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "app.core" in str(node.module):
                        for alias in node.names:
                            if alias.name == "Config":
                                has_config_import = True
                                break
                if has_config_import:
                    break

        assert has_config_import, (
            f"{module_name} 应依赖 Config（已知阻断点），但未检测到 import"
        )

    @pytest.mark.parametrize("module_name", PLUGIN_MODULES_WITHOUT_CONFIG_DEP)
    def test_module_has_no_config_dependency(self, module_name):
        """验证这些模块不应依赖 Config。"""
        import ast
        parts = module_name.split(".")
        module_path = WORKTREE.joinpath(*parts)
        if module_path.is_dir():
            module_path = module_path / "__init__.py"
        else:
            module_path = module_path.with_suffix(".py")

        if not module_path.exists():
            pytest.skip(f"{module_path} 不存在")

        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        has_config_import = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "app.core" in str(node.module):
                        for alias in node.names:
                            if alias.name == "Config":
                                has_config_import = True
                                break
                if has_config_import:
                    break

        assert not has_config_import, (
            f"{module_name} 不应依赖 Config，但检测到 import"
        )
