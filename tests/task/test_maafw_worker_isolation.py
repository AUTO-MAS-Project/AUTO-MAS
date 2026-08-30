"""worker 子进程的导入隔离 —— 第二层能否运行的硬前提。

worker 跑在 runtime pool 的隔离 venv 里，那里只有 `maafw`、`pydantic`、
`json5`、`json-with-comments`、`psutil`、`packaging` 与项目自己的依赖
（见 `RUNNER_DEFAULT_PACKAGES`）。**宿主的 httpx / loguru / fastapi 等一概没有。**

本文件钉死这条边界。它是回归测试，不是理论断言：移植期间这条边界曾被打破——
worker 的启动路径改成树内包路径后，`app/task/__init__.py` 与
`tools/core/__init__.py` 两个父包的 `__init__` 会各自急切拉起宿主，
worker 在隔离 venv 里以 `ModuleNotFoundError: httpx` 直接起不来。
"""

import builtins
import importlib
import unittest

import app.core  # noqa: F401  # 初始化宿主配置

WORKER_MODULE = "app.task.MaaFW.tools.core.automas_maafw_runner.worker"

# 隔离 venv 里不会存在的宿主专属包（取自实测的宿主导入面）
HOST_ONLY_PACKAGES = frozenset(
    {
        "Crypto",
        "PIL",
        "aiofiles",
        "anyio",
        "certifi",
        "click",
        "colorama",
        "cv2",
        "fastapi",
        "httpcore",
        "httpx",
        "idna",
        "jinja2",
        "keyboard",
        "loguru",
        "markupsafe",
        "onnxruntime",
        "plyer",
        "pyautogui",
        "pygetwindow",
        "pymsgbox",
        "pyperclip",
        "pyscreeze",
        "python_multipart",
        "rapidocr_onnxruntime",
        "rich",
        "starlette",
        "tomli_w",
        "truststore",
        "urllib3",
        "uvicorn",
        "win32api",
        "win32con",
        "win32crypt",
        "win32gui",
        "win32process",
        "yaml",
    }
)


class _BlockHostOnlyImports:
    """让宿主专属包的导入直接失败，模拟隔离 venv。"""

    def __init__(self) -> None:
        self._real = builtins.__import__
        self.blocked: list[str] = []

    def __enter__(self) -> "_BlockHostOnlyImports":
        def guard(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".")[0] in HOST_ONLY_PACKAGES:
                self.blocked.append(name)
                raise ImportError(f"host-only package is unavailable: {name}")
            return self._real(name, globals, locals, fromlist, level)

        builtins.__import__ = guard
        return self

    def __exit__(self, *exc_info) -> None:
        builtins.__import__ = self._real


class WorkerImportIsolationTest(unittest.TestCase):
    def test_worker_imports_without_any_host_only_package(self) -> None:
        # 先把已缓存的模块清掉，否则 import 直接命中 sys.modules 测不出问题
        import sys

        prefix = "app.task.MaaFW.tools"
        cached = [name for name in sys.modules if name.startswith(prefix)]
        saved = {name: sys.modules.pop(name) for name in cached}
        # 两个父包的 __init__ 也要重新执行
        for parent in ("app.task", "app.task.MaaFW"):
            if parent in sys.modules:
                saved[parent] = sys.modules.pop(parent)
        try:
            with _BlockHostOnlyImports():
                module = importlib.import_module(WORKER_MODULE)
            self.assertTrue(callable(module.main))
        finally:
            sys.modules.update(saved)

    def test_parent_packages_do_not_eagerly_import_submodules(self) -> None:
        """两个父包必须是惰性导出，否则 worker 的导入链会被拖回宿主。"""

        import app.task
        import app.task.MaaFW.tools.core as core

        for package in (app.task, core):
            with self.subTest(package=package.__name__):
                self.assertTrue(
                    hasattr(package, "_LAZY_EXPORTS"),
                    f"{package.__name__} 必须惰性导出",
                )

    def test_lazy_exports_still_resolve(self) -> None:
        """惰性化不得改变属性访问语义。"""

        import app.task as task
        import app.task.MaaFW.tools.core as core

        self.assertTrue(callable(task.MaaFWManager))
        self.assertTrue(callable(task.MaaFWEmbeddedManager))
        self.assertTrue(callable(core.MaaFWInterfaceService))
        self.assertTrue(callable(core.MaaFWProjectUpdateService))

    def test_unknown_attribute_still_raises(self) -> None:
        import app.task as task

        with self.assertRaises(AttributeError):
            task.NoSuchManager  # noqa: B018


class RunnerVenvPackageSetTest(unittest.TestCase):
    def test_worker_own_dependencies_are_installed_into_the_runner_venv(self) -> None:
        """worker 自己要用的第三方包必须由 runner venv 提供。

        `runner`/`worker` 用 psutil（含并入自 mfwa 的宿主看门狗），
        `runtime_pool` 用 packaging。插件形态下它们由插件目录经 PYTHONPATH
        提供，树内没有那一层。
        """

        from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
            RUNNER_DEFAULT_PACKAGES,
        )

        names = {
            package.split("==")[0].split(">")[0].split("<")[0].strip()
            for package in RUNNER_DEFAULT_PACKAGES
        }
        for required in ("maafw", "pydantic", "json5", "psutil", "packaging"):
            with self.subTest(package=required):
                self.assertIn(required, names)


class WorkerLaunchPathTest(unittest.TestCase):
    def test_launch_sites_use_the_in_tree_module_path(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        sites = (
            root / "app/task/MaaFW/tools/core/automas_maafw_runner/service.py",
            root / "app/task/MaaFW/tools/embedded/runner_task.py",
        )
        for path in sites:
            source = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                self.assertIn(
                    "app.task.MaaFW.tools.core.automas_maafw_runner.worker",
                    source,
                )

    def test_runner_task_puts_the_repo_root_on_the_worker_import_path(self) -> None:
        """隔离 venv 找不到本仓代码，必须经 import_paths 显式给出。"""

        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "app/task/MaaFW/tools/embedded/runner_task.py"
        ).read_text(encoding="utf-8")
        self.assertIn("import_paths=[Path.cwd()]", source)


if __name__ == "__main__":
    unittest.main()
