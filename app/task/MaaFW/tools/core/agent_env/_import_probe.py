"""Agent 导入静态检查的探针：由 ``import_check.py`` 以 ``python -B -c <本文件源码>``
在**项目自己的解释器**里执行，请求（JSON）从 stdin 读，结论（一行 JSON）写到 stdout。

不导入、不执行项目的任何代码：

- 子进程的 cwd 是一个空的临时目录（``-c`` 会把 ``''`` 即 cwd 插在 sys.path 最前，探针
  自己的 ``import json`` 之类在那一刻解析；cwd 若是项目根，根下的 ``json.py`` 就被执行了）。
  项目路径全部显式传入；``''`` 在探针自己的导入全部完成后才换成入口目录。
- 探针会用到、可能被惰性导入的标准库（``warnings`` / ``linecache`` / ``tokenize`` /
  ``token``：``ast.parse`` 遇到无效转义发 SyntaxWarning，显示警告时才导入它们）在改
  sys.path 之前全部预先导入，解析时再把警告整个压掉。
- 源码只用 ``ast`` 解析（项目解释器的语法版本）。
- 顶层名用 ``importlib.util.find_spec``：不带点的名字不会导入父包，只问 meta_path 上的
  finder（内置、冻结、路径，以及解释器 .pth 装的 finder，这些真跑 agent 时同样在）。
- 子模块**只看文件系统**：在每个候选父目录里依次认 ``名/``（带 ``__init__`` 的包或
  namespace 目录）、``名.py`` / ``.pyw``、扩展模块、``名.pyc``、``__pycache__/名.*.pyc``。
  不经 finder：``PathFinder.find_spec("a.b", [a 目录])`` 遇到 namespace 子目录要读
  ``sys.modules["a"].__path__``，父包没导入就抛 ``KeyError``（3.12 / 3.13 实测），吞成
  「没找到」就会把 MPA 这样的合法项目误拒。

sys.path 口径与真实启动 ``python <入口>.py`` 一致：环境变量由调用方照 agent 子进程设好；
``-c`` 插的 ``''`` 换成入口脚本所在目录（解释器带 ``._pth`` 或设了 safe_path 时两种启动
方式都不插，维持原样）。真实 agent 的 cwd（项目根）不在它的 sys.path 上，所以探针的 cwd
换成临时目录不改变判定。agent 常在运行时自己 ``sys.path.insert``（M9A 插 ``agent/``，
MaaFgo 插 ``agent/custom`` 与 ``agent/``），所以找项目自己的代码时另外把入口目录下每个
放着 Python 代码的目录和项目根都当成候选根——多认不少认，宁可漏报。

只用标准库、兼容 Python 3.8：项目自带的解释器版本不由我们定。
"""

from __future__ import annotations

# 下面这些必须在改 sys.path 之前导入完（见模块说明）
import ast
import importlib.util
import json
import linecache  # noqa: F401 - 预先导入，免得警告显示时从项目目录惰性导入
import os
import sys
import time
import token  # noqa: F401
import tokenize  # noqa: F401
import warnings
from importlib.machinery import BYTECODE_SUFFIXES, EXTENSION_SUFFIXES
from importlib.machinery import SOURCE_SUFFIXES as PY_SOURCE_SUFFIXES

# 走目录时不进这些（运行期产物、别人的包、版本库）
SKIP_DIR_NAMES = frozenset(
    {"__pycache__", ".pycache", "site-packages", "dist-packages", "node_modules"}
)
# 入口目录树的条目上限：超了就整份放弃（候选根不全会把「其实在」判成「不在」）
MAX_WALK_ENTRIES = 50000
# 兄弟目录排查时整个项目树的条目上限：超了就不再拒绝，只提示
MAX_INDEX_ENTRIES = 300000
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
SOURCE_SUFFIXES = tuple(PY_SOURCE_SUFFIXES)
MODULE_SUFFIXES = tuple(
    dict.fromkeys(
        list(PY_SOURCE_SUFFIXES) + list(EXTENSION_SUFFIXES) + list(BYTECODE_SUFFIXES)
    )
)
# 读不了的目录：查找结果「无法判定」，只提示不拒绝
UNKNOWN = object()


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _is_under(path, root):
    path = _norm(path)
    root = _norm(root)
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


class Found:
    """在某个目录里找到的一个模块或包（只是文件系统事实，没有导入任何东西）。"""

    __slots__ = ("dirs", "file", "init", "dynamic")

    def __init__(self, dirs=(), file=None, init=None, dynamic=False):
        self.dirs = list(dirs)
        self.file = file
        self.init = init
        self.dynamic = dynamic


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
        self.listings = {}
        self.top_cache = {}
        self.init_dynamic_cache = {}
        self.parsed = {}
        self.missing = []
        self.soft_missing = []
        self.external_missing = {}
        self.unparsable = []
        # 目录名 → 目录（兄弟目录排查用）；入口树走一遍时顺手记，其余部分按需补
        self.dir_index = {}
        self.dir_index_complete = None

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
        # 只认 ''，与 cwd 在哪无关。
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

    def _index_dir(self, path):
        key = os.path.normcase(os.path.basename(path))
        self.dir_index.setdefault(key, []).append(_norm(path))

    def _walk(self, start, limit, on_dir, skip=None):
        """深度优先走目录树；返回 None 或超限原因。跳过解释器目录、venv、运行期目录。"""

        seen_entries = 0
        stack = [start]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            seen_entries += len(entries)
            if seen_entries > limit:
                return "too_many"
            if any(entry.name == "pyvenv.cfg" for entry in entries):
                continue
            subdirs = []
            for entry in entries:
                name = entry.name
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                if not is_dir:
                    continue
                if name.startswith(".") or name in SKIP_DIR_NAMES:
                    continue
                if name.endswith((".dist-info", ".egg-info")):
                    continue
                if not self.is_code_location(entry.path):
                    continue
                if skip is not None and _norm(entry.path) == skip:
                    continue
                subdirs.append(entry.path)
            reason = on_dir(current, entries, subdirs)
            if reason is not None:
                return reason
            stack.extend(sorted(subdirs, reverse=True))
        return None

    def walk_entry_tree(self):
        """入口目录树里每个放着代码的目录都当候选根；顺带收集全部源码文件。"""

        if not self.is_code_location(self.entry_dir):
            return "入口脚本不在项目代码目录里"
        roots = [self.entry_dir]

        def on_dir(current, entries, subdirs):
            has_code = False
            for path in subdirs:
                self._index_dir(path)
                if self.dir_has_code(path, init_only=True):
                    has_code = True
            for entry in entries:
                if entry.name.endswith(SOURCE_SUFFIXES):
                    try:
                        if not entry.is_file():
                            continue
                    except OSError:
                        continue
                    has_code = True
                    self.source_files.append(_norm(entry.path))
                    if len(self.source_files) > MAX_SOURCE_FILES:
                        return "入口目录下的 Python 文件太多"
            if has_code and current != self.entry_dir:
                roots.append(current)
            return None

        reason = self._walk(self.entry_dir, MAX_WALK_ENTRIES, on_dir)
        if reason == "too_many":
            return "入口目录下的文件太多"
        if reason is not None:
            return reason
        roots.append(self.project)
        self.roots = [_norm(item) for item in dict.fromkeys(roots)]
        return None

    def complete_dir_index(self):
        """把入口树以外的项目目录也记进 ``dir_index``（只在要拒绝时才走）；超限返回 False。"""

        if self.dir_index_complete is None:
            entry_dir = _norm(self.entry_dir)
            if entry_dir == self.project:
                self.dir_index_complete = True
            else:

                def on_dir(current, entries, subdirs):
                    for path in subdirs:
                        self._index_dir(path)
                    return None

                reason = self._walk(
                    self.project, MAX_INDEX_ENTRIES, on_dir, skip=entry_dir
                )
                self.dir_index_complete = reason is None
        return self.dir_index_complete

    def has_sibling_package(self, name, known_dirs):
        """项目里（入口树内外）还有别的同名包目录：agent 可能在运行时插了它所在的目录。"""

        if not self.complete_dir_index():
            return True
        known = {_norm(item) for item in known_dirs}
        for path in self.dir_index.get(os.path.normcase(name), []):
            if path not in known and self.dir_has_code(path):
                return True
        return False

    # ---- 文件系统查找 ----

    def listing(self, directory):
        """``{normcase(名字): (真名, 是否目录)}``；读不了返回 None。"""

        key = _norm(directory)
        if key not in self.listings:
            result = None
            try:
                result = {}
                for entry in os.scandir(directory):
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    result[os.path.normcase(entry.name)] = (entry.name, is_dir)
            except OSError:
                result = None
            self.listings[key] = result
        return self.listings[key]

    def dir_has_code(self, path, init_only=False):
        entries = self.listing(path)
        if not entries:
            return False
        for suffix in MODULE_SUFFIXES:
            if os.path.normcase("__init__" + suffix) in entries:
                return True
        if init_only:
            return False
        return any(
            not is_dir and name.endswith(SOURCE_SUFFIXES)
            for name, is_dir in entries.values()
        )

    def find_in_dir(self, directory, name):
        """``directory`` 里名为 ``name`` 的模块或包 → ``Found`` / None / ``UNKNOWN``。

        大小写按文件系统不敏感比对（Windows 上 import 其实区分大小写：多认不少认）。
        包目录与同名模块并存时（真实导入取包或模块，看有没有 ``__init__``），标成
        dynamic，底下缺东西也只提示。
        """

        try:
            entries = self.listing(directory)
            if entries is None:
                return UNKNOWN
            key = os.path.normcase(name)
            module_file = None
            for suffix in MODULE_SUFFIXES:
                hit = entries.get(os.path.normcase(name + suffix))
                if hit is not None and not hit[1]:
                    module_file = os.path.join(directory, hit[0])
                    break
            hit = entries.get(key)
            if hit is not None and hit[1]:
                package_dir = os.path.join(directory, hit[0])
                sub = self.listing(package_dir)
                if sub is None:
                    return UNKNOWN
                init = None
                for suffix in MODULE_SUFFIXES:
                    init_hit = sub.get(os.path.normcase("__init__" + suffix))
                    if init_hit is not None and not init_hit[1]:
                        init = os.path.join(package_dir, init_hit[0])
                        break
                return Found(
                    dirs=[package_dir],
                    file=init if init and init.endswith(SOURCE_SUFFIXES) else None,
                    init=init,
                    dynamic=init is None and module_file is not None,
                )
            if module_file is not None:
                return Found(
                    file=module_file if module_file.endswith(SOURCE_SUFFIXES) else None
                )
            cache = entries.get("__pycache__")
            if cache is not None and cache[1]:
                cached = self.listing(os.path.join(directory, cache[0])) or {}
                prefix = os.path.normcase(name) + "."
                for cached_name in cached:
                    if cached_name.startswith(prefix) and cached_name.endswith(".pyc"):
                        return Found()
            return None
        except Exception:  # noqa: BLE001 - 查找本身出错：无法判定
            return UNKNOWN

    def find_all(self, name, dirs):
        """在每个目录里各找一次；返回 ``(找到的, 是否有目录无法判定)``。"""

        found = []
        uncertain = False
        for directory in dirs:
            result = self.find_in_dir(directory, name)
            if result is UNKNOWN:
                uncertain = True
            elif result is not None:
                found.append(result)
        return found, uncertain

    def found_is_dynamic(self, found):
        if found.dynamic:
            return True
        init = found.init
        if not init:
            return False
        key = _norm(init)
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

    def found_from_spec(self, spec):
        dirs = []
        try:
            locations = spec.submodule_search_locations
            if locations:
                dirs = [str(item) for item in locations]
        except Exception:  # noqa: BLE001
            return None
        origin = spec.origin
        if origin in ("namespace", "built-in", "frozen"):
            origin = None
        file = origin if origin and origin.endswith(SOURCE_SUFFIXES) else None
        return Found(dirs=dirs, file=file, init=origin if dirs else None)

    def found_in_project(self, found):
        paths = list(found.dirs) + [item for item in (found.file, found.init) if item]
        return bool(paths) and all(self.is_code_location(item) for item in paths)

    def classify_top(self, name):
        """顶层名 → ``(kind, founds, uncertain)``；kind 是 external / project / missing。"""

        cached = self.top_cache.get(name)
        if cached is not None:
            return cached
        result = ("missing", [], False)
        if name in sys.builtin_module_names:
            result = ("external", [], False)
        else:
            real = None
            real_failed = False
            try:
                real = importlib.util.find_spec(name)
            except Exception:  # noqa: BLE001 - finder 报错不代表不在，按外部处理
                real_failed = True
            real_found = self.found_from_spec(real) if real is not None else None
            if real_failed or (real is not None and real_found is None):
                result = ("external", [], False)
            elif real_found is not None and not self.found_in_project(real_found):
                result = ("external", [], False)
            else:
                founds = [real_found] if real_found is not None else []
                extra, uncertain = self.find_all(name, self.roots)
                founds.extend(item for item in extra if self.found_in_project(item))
                if founds:
                    result = ("project", founds, uncertain)
                elif uncertain:
                    result = ("external", [], True)
        self.top_cache[name] = result
        return result

    @staticmethod
    def code_dirs(founds):
        dirs = []
        for found in founds:
            dirs.extend(found.dirs)
        return list(dict.fromkeys(dirs))

    def resolve_chain(self, parts, founds, uncertain=False):
        """从已找到的第一段沿 ``parts`` 往下找。

        返回 ``(status, 缺的全名, 途经的源码文件, 最后一级)``；status 是 ok / missing /
        soft（缺了但不下结论）/ not_package。
        """

        files = [found.file for found in founds if found.file]
        soft = uncertain or any(self.found_is_dynamic(found) for found in founds)
        for index in range(1, len(parts)):
            dirs = [
                item for item in self.code_dirs(founds) if self.is_code_location(item)
            ]
            fullname = ".".join(parts[: index + 1])
            if not dirs:
                return "not_package", fullname, files, []
            founds, unknown = self.find_all(parts[index], dirs)
            if not founds:
                # 父目录里一行代码都没有（只是同名的数据目录），也不下结论
                if soft or unknown or not any(self.dir_has_code(d) for d in dirs):
                    return "soft", fullname, files, []
                return "missing", fullname, files, dirs
            files.extend(found.file for found in founds if found.file)
            if unknown or any(self.found_is_dynamic(found) for found in founds):
                soft = True
        return "ok", None, files, founds

    def submodule_files(self, founds, names):
        """``from X import a, b``：a / b 若恰是子模块，把它们的源码也算进来（不报缺）。"""

        dirs = [item for item in self.code_dirs(founds) if self.is_code_location(item)]
        files = []
        for name in names:
            if name == "*":
                continue
            found, _ = self.find_all(name, dirs)
            files.extend(item.file for item in found if item.file)
        return files

    # ---- 源码扫描 ----

    def parse(self, path):
        if path in self.parsed:
            return self.parsed[path]
        tree = None
        try:
            if os.path.getsize(path) <= MAX_SOURCE_BYTES:
                with open(path, "rb") as handle:
                    source = handle.read()
                # 无效转义等会发 SyntaxWarning；显示警告要惰性导入 linecache 等，
                # 而此刻 sys.path 最前面已是项目目录
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    tree = ast.parse(source, filename=path)
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
        kind, founds, uncertain = self.classify_top(parts[0])
        if kind == "external":
            return []
        if kind == "missing":
            if hard and startup:
                self.external_missing.setdefault(
                    parts[0], {"file": self.rel(path), "line": node.lineno}
                )
            return []
        status, fullname, files, last = self.resolve_chain(parts, founds, uncertain)
        if status == "missing":
            # 项目里别处还有同名的包目录：agent 可能运行时把那里插进了 sys.path
            if (
                hard
                and startup
                and self.has_sibling_package(parts[0], self.code_dirs(founds))
            ):
                hard = False
            self.record_missing(fullname, path, node, hard, startup)
            return []
        if status == "soft":
            self.record_missing(fullname, path, node, False, startup)
            return []
        if status != "ok":
            return []
        if names:
            files.extend(self.submodule_files(last, names))
        return files

    def check_relative(self, node, path, hard, startup):
        base = os.path.dirname(path)
        for _ in range(node.level - 1):
            base = os.path.dirname(base)
        if not self.is_code_location(base):
            return []
        # 所在目录不是包时相对导入根本起不来，这不是「缺模块」，不下结论
        in_package = self.dir_has_code(os.path.dirname(path), init_only=True)
        names = [alias.name for alias in node.names]
        if not node.module:
            files = []
            for name in names:
                if name == "*":
                    continue
                found, _ = self.find_all(name, [base])
                files.extend(item.file for item in found if item.file)
            return files
        parts = node.module.split(".")
        founds, uncertain = self.find_all(parts[0], [base])
        package = self.package_name(base)
        display_prefix = package + "." if package else "." * node.level
        if not founds:
            if in_package:
                self.record_missing(
                    display_prefix + parts[0],
                    path,
                    node,
                    hard and not uncertain,
                    startup,
                )
            return []
        status, fullname, files, last = self.resolve_chain(parts, founds, uncertain)
        if status in ("missing", "soft"):
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
            files.extend(self.submodule_files(last, names))
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
            path = _norm(queue.pop(0))
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
