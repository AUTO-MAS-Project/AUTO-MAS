"""Agent 导入静态检查的探针：由 ``import_check.py`` 以 ``python -B -c <本文件源码>``
在**项目自己的解释器**里执行，请求（JSON）从 stdin 读，结论（一行 JSON）写到 stdout。

不导入、不执行项目的任何代码：

- 源码只用 ``ast`` 解析（用的是项目解释器的语法版本，3.13 的写法不会被宿主 3.12 误判）；
- 顶层名用 ``importlib.util.find_spec``——不带点的名字不会导入父包，只问 meta_path 上的
  finder（内置、冻结、路径，以及解释器 .pth 装的 finder，这些真跑 agent 时同样在）；
- 子模块用 ``importlib.machinery.PathFinder.find_spec(全名, [包目录])`` 逐级在目录里找，
  包的 ``__init__`` 不执行（``importlib.util.find_spec("a.b")`` 会先 import ``a``，不能用）。

sys.path 口径与真实启动 ``python <入口>.py`` 一致：环境变量、cwd 由调用方照 agent 子进程
设好；``-c`` 插在最前面的 ``''`` 换成入口脚本所在目录（解释器带 ``._pth`` 或设了
safe_path 时两种启动方式都不插，维持原样）。agent 常在运行时自己 ``sys.path.insert``
（M9A 插 ``agent/``，MaaFgo 插 ``agent/custom`` 与 ``agent/``），所以找项目自己的代码时
另外把入口目录下每个放着 Python 代码的目录和项目根都当成候选根——多认不少认，宁可漏报。

只用标准库、兼容 Python 3.8：项目自带的解释器版本不由我们定。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import time
from importlib.machinery import PathFinder

# 走目录时不进这些（运行期产物、别人的包、版本库）
SKIP_DIR_NAMES = frozenset(
    {"__pycache__", ".pycache", "site-packages", "dist-packages", "node_modules"}
)
# 入口目录树的条目上限：超了就整份放弃（候选根不全会把「其实在」判成「不在」）
MAX_WALK_ENTRIES = 50000
MAX_SOURCE_FILES = 5000
MAX_SOURCE_BYTES = 4 * 1024 * 1024
# 包的 __init__ 里出现这些，子模块可能是运行时造出来的：找不到也只提示
DYNAMIC_INIT_MARKERS = (
    "__path__",
    "extend_path",
    "declare_namespace",
    "sys.modules",
    "__getattr__",
)
IMPORT_ERROR_NAMES = frozenset(
    {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
)
SOURCE_SUFFIXES = (".py", ".pyw")


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _is_under(path, root):
    path = _norm(path)
    root = _norm(root)
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


class Probe:
    def __init__(self, project, entry, pythonpath=""):
        self.pythonpath = pythonpath
        self.project = _norm(project)
        self.entry = _norm(entry)
        self.entry_dir = os.path.dirname(self.entry)
        interpreter_dirs = {
            os.path.dirname(sys.executable or ""),
            sys.prefix,
            sys.base_prefix,
            sys.exec_prefix,
        }
        self.interpreter_dirs = [_norm(item) for item in interpreter_dirs if item]
        self.roots = []
        self.source_files = []
        self.top_cache = {}
        self.init_dynamic_cache = {}
        self.parsed = {}
        self.missing = []
        self.soft_missing = []
        self.external_missing = {}
        self.unparsable = []

    # ---- 位置判定 ----

    def is_code_location(self, path):
        if not path or not _is_under(path, self.project):
            return False
        return not any(_is_under(path, item) for item in self.interpreter_dirs)

    def rel(self, path):
        try:
            return os.path.relpath(path, self.project).replace(os.sep, "/")
        except ValueError:
            return path

    # ---- sys.path 与候选根 ----

    def emulate_script_path(self, pythonpath):
        # ``python -c`` 把 '' 插在最前；``python 入口.py`` 插的是入口所在目录。
        if sys.path and sys.path[0] == "":
            sys.path[0] = self.entry_dir
            insert_at = 1
        else:
            insert_at = 0
        # agent 子进程的 PYTHONPATH（项目根）不经环境变量传进来：解释器启动时会从它
        # import sitecustomize / usercustomize，那就执行了项目代码。这里按解释器自己的
        # 规则补回同一位置（紧跟脚本目录）；._pth / -I / -E 下本来就不认它。
        if pythonpath and not sys.flags.ignore_environment:
            sys.path[insert_at:insert_at] = [
                item for item in pythonpath.split(os.pathsep) if item
            ]

    def walk_entry_tree(self):
        """入口目录树里每个放着代码的目录都当候选根；顺带收集全部源码文件。"""

        if not self.is_code_location(self.entry_dir):
            return "入口脚本不在项目代码目录里"
        roots = [self.entry_dir]
        seen_entries = 0
        stack = [self.entry_dir]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            seen_entries += len(entries)
            if seen_entries > MAX_WALK_ENTRIES:
                return "入口目录下的文件太多"
            has_code = False
            subdirs = []
            for entry in entries:
                name = entry.name
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                if is_dir:
                    if name.startswith(".") or name in SKIP_DIR_NAMES:
                        continue
                    if name.endswith((".dist-info", ".egg-info")):
                        continue
                    if not self.is_code_location(entry.path):
                        continue
                    subdirs.append(entry.path)
                    if os.path.isfile(os.path.join(entry.path, "__init__.py")):
                        has_code = True
                elif name.endswith(SOURCE_SUFFIXES):
                    has_code = True
                    self.source_files.append(_norm(entry.path))
                    if len(self.source_files) > MAX_SOURCE_FILES:
                        return "入口目录下的 Python 文件太多"
            if has_code and current != self.entry_dir:
                roots.append(current)
            stack.extend(sorted(subdirs, reverse=True))
        roots.append(self.project)
        self.roots = [_norm(item) for item in dict.fromkeys(roots)]
        return None

    # ---- 模块解析 ----

    @staticmethod
    def spec_dirs(spec):
        locations = getattr(spec, "submodule_search_locations", None)
        return [str(item) for item in locations] if locations else []

    @staticmethod
    def spec_is_regular(spec):
        return spec.origin not in (None, "namespace")

    def dir_has_code(self, path):
        if os.path.isfile(os.path.join(path, "__init__.py")):
            return True
        try:
            return any(name.endswith(SOURCE_SUFFIXES) for name in os.listdir(path))
        except OSError:
            return False

    def spec_files(self, spec):
        origin = spec.origin
        if origin and origin != "namespace" and origin.endswith(SOURCE_SUFFIXES):
            return [_norm(origin)]
        return []

    def init_is_dynamic(self, spec):
        origin = spec.origin
        if not origin or origin == "namespace":
            return False
        key = _norm(origin)
        if key not in self.init_dynamic_cache:
            dynamic = False
            if key.endswith(SOURCE_SUFFIXES):
                try:
                    with open(key, "rb") as handle:
                        text = handle.read(MAX_SOURCE_BYTES).decode("utf-8", "replace")
                    dynamic = any(marker in text for marker in DYNAMIC_INIT_MARKERS)
                except OSError:
                    dynamic = True
            else:
                # .pyd / .pyc 包入口看不到源码，按可能动态处理
                dynamic = True
            self.init_dynamic_cache[key] = dynamic
        return self.init_dynamic_cache[key]

    def find_in_dirs(self, fullname, dirs):
        found = []
        for directory in dirs:
            try:
                spec = PathFinder.find_spec(fullname, [directory])
            except Exception:  # noqa: BLE001 - 找不到就当不在
                spec = None
            if spec is not None:
                found.append(spec)
        return found

    def classify_top(self, name):
        """顶层名 → ``(kind, specs)``；kind 是 external / project / missing。"""

        cached = self.top_cache.get(name)
        if cached is not None:
            return cached
        result = ("missing", [])
        if name in sys.builtin_module_names:
            result = ("external", [])
        else:
            real = None
            real_failed = False
            try:
                real = importlib.util.find_spec(name)
            except Exception:  # noqa: BLE001 - finder 报错不代表不在，按外部处理
                real_failed = True
            if real_failed:
                result = ("external", [])
            elif real is not None and not self._spec_in_project(real):
                result = ("external", [real])
            else:
                specs = [real] if real is not None else []
                specs.extend(
                    spec
                    for spec in self.find_in_dirs(name, self.roots)
                    if self._spec_in_project(spec)
                )
                if specs:
                    result = ("project", specs)
        self.top_cache[name] = result
        return result

    def _spec_in_project(self, spec):
        origin = spec.origin
        if origin and origin not in ("namespace", "built-in", "frozen"):
            return self.is_code_location(origin)
        dirs = self.spec_dirs(spec)
        return bool(dirs) and all(self.is_code_location(item) for item in dirs)

    def resolve_chain(self, parts, specs):
        """从已找到的第一段（``specs``）沿 ``parts`` 往下找。

        返回 ``(status, 缺的全名, 途经的源码文件)``；status 是 ok / missing / dynamic /
        not_package。
        """

        files = []
        for spec in specs:
            files.extend(self.spec_files(spec))
        dynamic = any(
            self.init_is_dynamic(spec) for spec in specs if self.spec_dirs(spec)
        )
        for index in range(1, len(parts)):
            dirs = []
            for spec in specs:
                dirs.extend(
                    item
                    for item in self.spec_dirs(spec)
                    if self.is_code_location(item) and self.dir_has_code(item)
                )
            dirs = list(dict.fromkeys(dirs))
            fullname = ".".join(parts[: index + 1])
            if not dirs:
                return "not_package", fullname, files
            specs = self.find_in_dirs(fullname, dirs)
            if not specs:
                return ("dynamic" if dynamic else "missing"), fullname, files
            for spec in specs:
                files.extend(self.spec_files(spec))
            if any(
                self.init_is_dynamic(spec) for spec in specs if self.spec_dirs(spec)
            ):
                dynamic = True
        return "ok", None, files

    def submodule_files(self, parts, specs, names):
        """``from X import a, b``：a / b 若恰是子模块，把它们的源码也算进来（不报缺）。"""

        dirs = []
        for spec in specs:
            dirs.extend(
                item for item in self.spec_dirs(spec) if self.is_code_location(item)
            )
        files = []
        for name in names:
            if name == "*":
                continue
            for spec in self.find_in_dirs(".".join([*parts, name]), dirs):
                files.extend(self.spec_files(spec))
        return files

    def final_specs(self, parts, specs):
        for index in range(1, len(parts)):
            dirs = []
            for spec in specs:
                dirs.extend(
                    item for item in self.spec_dirs(spec) if self.is_code_location(item)
                )
            specs = self.find_in_dirs(".".join(parts[: index + 1]), dirs)
            if not specs:
                return []
        return specs

    # ---- 源码扫描 ----

    def parse(self, path):
        if path in self.parsed:
            return self.parsed[path]
        tree = None
        try:
            if os.path.getsize(path) <= MAX_SOURCE_BYTES:
                with open(path, "rb") as handle:
                    tree = ast.parse(handle.read(), filename=path)
        except (OSError, SyntaxError, ValueError):
            self.unparsable.append(self.rel(path))
            tree = None
        self.parsed[path] = tree
        return tree

    def collect_imports(self, tree):
        """``[(node, hard)]``：hard = 模块导入时必然执行、失败没人接住。"""

        found = []

        def is_type_checking(test):
            if isinstance(test, ast.Name):
                return test.id == "TYPE_CHECKING"
            if isinstance(test, ast.Attribute):
                return test.attr == "TYPE_CHECKING"
            return False

        def catches_import_error(handlers):
            for handler in handlers:
                kind = handler.type
                if kind is None:
                    return True
                names = kind.elts if isinstance(kind, ast.Tuple) else [kind]
                for item in names:
                    name = (
                        item.id
                        if isinstance(item, ast.Name)
                        else getattr(item, "attr", "")
                    )
                    if name in IMPORT_ERROR_NAMES:
                        return True
            return False

        try_types = tuple(
            item
            for item in (getattr(ast, "Try", None), getattr(ast, "TryStar", None))
            if item is not None
        )

        def visit(body, hard):
            for node in body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    found.append((node, hard))
                elif isinstance(node, ast.If):
                    if is_type_checking(node.test):
                        visit(node.orelse, False)
                        continue
                    visit(node.body, False)
                    visit(node.orelse, False)
                elif try_types and isinstance(node, try_types):
                    visit(node.body, hard and not catches_import_error(node.handlers))
                    for handler in node.handlers:
                        visit(handler.body, False)
                    visit(node.orelse, hard)
                    visit(node.finalbody, hard)
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    visit(node.body, hard)
                else:
                    # 函数 / 类体 / 循环 / match：不一定在导入时执行，一律只提示
                    for field in ("body", "orelse", "finalbody"):
                        children = getattr(node, field, None)
                        if isinstance(children, list):
                            visit(children, False)
                    for field in ("handlers", "cases"):
                        for child in getattr(node, field, None) or []:
                            visit(getattr(child, "body", None) or [], False)

        visit(tree.body, True)
        return found

    def package_name(self, directory):
        """``directory`` 作为包时的点分名，只用于文案；取从各候选根能导入的最短那个。

        M9A 的 ``agent/utils`` 往上数 ``agent/`` 也有 ``__init__.py``，但 agent 把
        ``agent/`` 插进 sys.path、按 ``utils`` 导入它，写成 ``agent.utils`` 会误导人。
        """

        target = _norm(directory)
        best = None
        for root in list(self.roots) + [item for item in sys.path if item]:
            base = _norm(root)
            if target == base or not _is_under(target, base):
                continue
            parts = os.path.relpath(target, base).split(os.sep)
            current = base
            for part in parts:
                current = os.path.join(current, part)
                if not os.path.isfile(os.path.join(current, "__init__.py")):
                    break
            else:
                if best is None or len(parts) < len(best):
                    best = parts
        return ".".join(best) if best else None

    def check_file(self, path, startup):
        """扫一个文件；返回启动时会被连带执行的项目源码文件。"""

        tree = self.parse(path)
        if tree is None:
            return []
        followers = []
        for node, hard in self.collect_imports(tree):
            if isinstance(node, ast.Import):
                files = []
                for alias in node.names:
                    files.extend(
                        self.check_absolute(alias.name, [], node, path, hard, startup)
                    )
            elif node.level:
                files = self.check_relative(node, path, hard, startup)
            elif node.module:
                names = [alias.name for alias in node.names]
                files = self.check_absolute(
                    node.module, names, node, path, hard, startup
                )
            else:
                files = []
            # 只有导入时必然执行的导入会把目标拖进「启动时执行」的集合
            if hard:
                followers.extend(files)
        return followers

    def record_missing(self, fullname, path, node, hard, startup):
        item = {"module": fullname, "file": self.rel(path), "line": node.lineno}
        if hard and startup:
            self.missing.append(item)
        else:
            self.soft_missing.append(item)

    def check_absolute(self, module, names, node, path, hard, startup):
        parts = module.split(".")
        kind, specs = self.classify_top(parts[0])
        if kind == "external":
            return []
        if kind == "missing":
            if hard and startup:
                self.external_missing.setdefault(
                    parts[0], {"file": self.rel(path), "line": node.lineno}
                )
            return []
        status, fullname, files = self.resolve_chain(parts, specs)
        if status == "missing":
            self.record_missing(fullname, path, node, hard, startup)
            return []
        if status == "dynamic":
            self.record_missing(fullname, path, node, False, startup)
            return []
        if status != "ok":
            return []
        if names:
            files.extend(
                self.submodule_files(parts, self.final_specs(parts, specs), names)
            )
        return files

    def check_relative(self, node, path, hard, startup):
        base = os.path.dirname(path)
        for _ in range(node.level - 1):
            base = os.path.dirname(base)
        if not self.is_code_location(base):
            return []
        # 所在目录不是包时相对导入根本起不来，这不是「缺模块」，不下结论
        in_package = os.path.isfile(os.path.join(os.path.dirname(path), "__init__.py"))
        names = [alias.name for alias in node.names]
        package = self.package_name(base)
        if not node.module:
            files = []
            for name in names:
                if name == "*":
                    continue
                for spec in self.find_in_dirs(name, [base]):
                    files.extend(self.spec_files(spec))
            return files
        parts = node.module.split(".")
        specs = self.find_in_dirs(parts[0], [base])
        display_prefix = package + "." if package else "." * node.level
        if not specs:
            if in_package:
                self.record_missing(
                    display_prefix + parts[0], path, node, hard, startup
                )
            return []
        status, fullname, files = self.resolve_chain(parts, specs)
        if status in ("missing", "dynamic"):
            if in_package:
                self.record_missing(
                    display_prefix + fullname,
                    path,
                    node,
                    hard and status == "missing",
                    startup,
                )
            return []
        if status != "ok":
            return []
        if names:
            files.extend(
                self.submodule_files(parts, self.final_specs(parts, specs), names)
            )
        return files

    def run(self):
        started = time.perf_counter()
        self.emulate_script_path(self.pythonpath)
        reason = self.walk_entry_tree()
        if reason is not None:
            return {"checked": False, "reason": reason}
        startup = []
        queue = [self.entry]
        seen = set()
        while queue:
            path = queue.pop(0)
            if path in seen or not self.is_code_location(path):
                continue
            seen.add(path)
            startup.append(path)
            queue.extend(self.check_file(path, True))
        for path in self.source_files:
            if path not in seen:
                seen.add(path)
                self.check_file(path, False)
        return {
            "checked": True,
            "missing": _dedupe(self.missing),
            "softMissing": _dedupe(self.soft_missing),
            "externalMissing": [
                dict(module=name, **where)
                for name, where in sorted(self.external_missing.items())
            ],
            "unparsable": sorted(set(self.unparsable)),
            "startupFiles": len(startup),
            "files": len(seen),
            "python": "%d.%d" % sys.version_info[:2],
            "elapsed": round(time.perf_counter() - started, 3),
        }


def _dedupe(items):
    seen = set()
    result = []
    for item in items:
        key = item["module"]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    request = json.loads(sys.stdin.read())
    try:
        result = Probe(
            request["project"], request["entry"], request.get("pythonpath") or ""
        ).run()
    except Exception as exc:  # noqa: BLE001 - 探针自己出错就放弃检查，不下结论
        result = {"checked": False, "reason": "%s: %s" % (type(exc).__name__, exc)}
    sys.stdout.write("\n" + json.dumps(result, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
