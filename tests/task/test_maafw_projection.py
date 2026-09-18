"""按 interface 白名单投影 MaaFW 发行包的纯逻辑回归。

投影是"只拿声明了的"，不是"删掉外壳"。每一条都是写错了不报错、只会让副本多出或
少掉文件的地方：白名单目标的口径（完整 / 保留根 / 豁免根名）、assets 布局的提升、
自带解释器被投影掉时不算错、差量包的叠加视图、以及 ``build_package_plan`` 三张表
一起过滤。夹具全部是临时目录里合成的迷你项目，不碰真实发行包。
"""

import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    apply_package_transaction,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.projection import (
    ProjectionError,
    build_projection_plan,
    build_projection_rules,
    classify_agent,
    exclusion_reason,
    filter_package_entries,
    materialize_projection,
    package_projection_rules,
)
from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
    pin_agent_maafw_requirement,
    probe_bundled_maafw_version,
    resolve_project_maafw_requirement,
)

# 照抄真实原生库里的排布（照 MaaFramework 发行包实际排布）：版本号是一条 NUL 结尾
# 的 C 字符串，前后都是别的字符串。
_DLL_TEMPLATE = (
    b"\x00\x00\x00\x00latest_id\x00\x00\x00\x00%s\x00DoNothing\x00\x00\x00MaaAdbC"
)


def _bundled_dll(version: str) -> bytes:
    return _DLL_TEMPLATE % version.encode("ascii")


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _interface(**overrides) -> str:
    payload = {
        "name": "Demo",
        "version": "v1.0.0",
        "resource": [{"name": "官服", "path": ["./resource/base"]}],
        "controller": [{"name": "ADB", "type": "Adb"}],
        "agent": {
            "child_exec": "./python/python.exe",
            "child_args": ["-u", "./agent/main.py"],
        },
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _release(root: Path, interface: str | None = None) -> Path:
    """一份带外壳的迷你 release 布局发行包。"""

    _write(root / "interface.json", interface or _interface())
    _write(root / "resource/base/pipeline/a.json", '{"A": {}}')
    _write(root / "resource/base/image/x.png", "png")
    _write(root / "resource/base/__pycache__/junk.pyc", "pyc")
    _write(root / "agent/main.py", "print('hi')")
    _write(root / "agent/__pycache__/main.cpython-312.pyc", "pyc")
    _write(root / "requirements.txt", "maafw\n")
    _write(root / "python/python.exe", "exe" * 100)
    _write(root / "python/python313.dll", "dll" * 100)
    _write(root / "MFW.exe", "shell" * 100)
    (root / "maafw").mkdir(exist_ok=True)
    (root / "maafw/MaaFramework.dll").write_bytes(_bundled_dll("v5.11.1"))
    _write(root / "libs/Avalonia.dll", "dll" * 100)
    _write(root / "runtimes/win-x64/native/x.dll", "dll" * 100)
    _write(root / "debug/maa.log", "log")
    _write(root / "README.md", "readme")
    return root


class TestWhitelist:
    def test_keeps_only_declared_payload(self, tmp_path: Path) -> None:
        plan = build_projection_plan(_release(tmp_path / "src"))
        kept = {path.as_posix() for path in plan.copied_files}

        assert kept == {
            "interface.json",
            "resource/base/pipeline/a.json",
            "resource/base/image/x.png",
            "agent/main.py",
            "requirements.txt",
            # 项目自带的运行时原样带走：agent 的解释器目录与 MaaFramework 原生库目录。
            "python/python.exe",
            "python/python313.dll",
            "maafw/MaaFramework.dll",
            # 白名单之外的小文件留下：agent 运行时读的数据常常没在 interface 里声明。
            "README.md",
        }
        reasons = plan.excluded_reasons
        assert reasons["MFW.exe"] == "ui-shell"
        # 外壳自己的运行时目录里没有 MaaFramework，照常剔除。
        assert reasons["runtimes/win-x64/native/x.dll"] == "embedded-runtime"
        assert reasons["agent/__pycache__/main.cpython-312.pyc"] == "cache"
        # 声明目录里的缓存也剔，白名单不是免检。
        assert reasons["resource/base/__pycache__/junk.pyc"] == "cache"
        # .NET 外壳的托管库目录按内容判掉，不看大小。
        assert reasons["libs/Avalonia.dll"] == "not-required-by-runtime-projection"
        assert reasons["debug/maa.log"] == "cache"

    def test_small_undeclared_entries_are_kept_and_large_ones_dropped(
        self, tmp_path: Path
    ) -> None:
        # MaaEnd 的 data/ 与 locales/、MaaYYs 的 assets/答案.csv 都没在 interface 里声明，
        # 却是 agent 运行时要读的；MFAAvalonia 的 libs/（141 MB）、M9A 的 temp_res
        # （185 MB）则是外壳运行时。剩余 ≤ 64 MB 的顶层条目留下，更大的丢，根上的
        # 可执行文件与库一律不要。
        root = _release(tmp_path / "src")
        _write(root / "data/activity/cn.json", "{}")
        _write(root / "locales/agent/zh_cn.json", "{}")
        _write(root / "resource/extra/shared.png", "png")
        _write(root / "changes.json", "{}")
        _write(root / "m9a.exe", "launcher")
        _write(root / "MaaDbgControlUnit.dll", "dll")
        huge = root / "temp_res/old/big.bin"
        huge.parent.mkdir(parents=True)
        with huge.open("wb") as handle:
            handle.truncate(65 * 1024 * 1024)

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert {
            "data/activity/cn.json",
            "locales/agent/zh_cn.json",
            "resource/extra/shared.png",
            "changes.json",
        } <= kept
        assert not any(path.startswith("temp_res/") for path in kept)
        assert "m9a.exe" not in kept and "MaaDbgControlUnit.dll" not in kept
        assert any("temp_res/" in warning for warning in plan.rules.warnings)

    def test_frozen_python_shell_packages_are_not_adopted(self, tmp_path: Path) -> None:
        # Maa_bbb 的外壳 MFW.exe 是冻结的 Python 程序：python312.dll 和 numpy / backports
        # 等二进制依赖包散在根目录。它们一个个都 ≤ 64 MB，却不能带——agent 子进程的
        # PYTHONPATH 是项目根，没有 __init__.py 的半截包会变成命名空间包盖住真正的模块
        # （副本上 pip 就是被 backports.zstd 打崩的）。纯数据目录与纯 Python 包照常留下。
        root = _release(tmp_path / "src")
        _write(root / "python312.dll", "dll" * 100)
        _write(root / "numpy/_core/_multiarray_umath.pyd", "pyd")
        _write(root / "numpy.libs/libscipy_openblas64_.dll", "dll")
        _write(root / "backports/zstd/_zstd.pyd", "pyd")
        _write(root / "certifi/cacert.pem", "pem")
        _write(root / "helpers/__init__.py", "")
        _write(root / "data/activity/cn.json", "{}")

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert not any(
            path.startswith(("numpy/", "numpy.libs/", "backports/")) for path in kept
        )
        assert {
            "certifi/cacert.pem",
            "helpers/__init__.py",
            "data/activity/cn.json",
        } <= kept
        assert "python312.dll" not in kept
        assert any("backports" in warning for warning in plan.rules.warnings)

    def test_binary_packages_stay_when_the_shell_is_not_frozen_python(
        self, tmp_path: Path
    ) -> None:
        # 根上没有 python3xx.dll 就不是冻结外壳：带 .pyd 的顶层目录可能是项目自己给
        # agent 准备的扩展（PYTHONPATH=项目根 正是为了它们），照 ≤ 64 MB 的口径留下。
        root = _release(tmp_path / "src")
        _write(root / "fastcv/_impl.pyd", "pyd")

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert "fastcv/_impl.pyd" in kept

    def test_ui_assets_named_by_interface_are_kept(self, tmp_path: Path) -> None:
        # AUTO-MAS 用户页会展示项目图标、任务图标与 welcome；这些不参与运行但要带上。
        # 图标路径常以 / 开头（项目根相对），远程 URL 与不存在的文件都静默跳过。
        interface = _interface(
            icon="/assets/logo/logo.png",
            welcome="README.md",
            task=[
                {"name": "A", "entry": "A", "icon": "./assets/icons/a.png"},
                {"name": "B", "entry": "B", "icon": "https://x/b.png"},
                {"name": "C", "entry": "C", "icon": "assets/icons/missing.png"},
            ],
            option={"opt": {"cases": [{"name": "c", "icon": "assets/icons/c.png"}]}},
        )
        root = _release(tmp_path / "src", interface)
        _write(root / "assets/logo/logo.png", "png")
        _write(root / "assets/icons/a.png", "png")
        _write(root / "assets/icons/c.png", "png")
        _write(root / "assets/screenshots/big.png", "png" * 100)

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert {
            "assets/logo/logo.png",
            "assets/icons/a.png",
            "assets/icons/c.png",
        } <= kept
        assert "README.md" in kept
        # assets/ 整体不到 64 MB，剩下的截图也一并留下（未声明的小目录整个带走）。
        assert "assets/screenshots/big.png" in kept
        assert not any("missing.png" in warning for warning in plan.rules.warnings)

    def test_bundled_runtime_is_kept_verbatim_for_python_agents_too(
        self, tmp_path: Path
    ) -> None:
        # runner 优先加载项目自带的原生库（可能是自定义构建），整目录带走，与路径模式一致。
        # 原样就是原样：分类表在里面不起作用——CPython 发行版本来就有叫 build / debug 的
        # 目录（Maa_bbb 的副本上 pip/_internal/operations/build 被投影掉，pip 起不来），
        # 无源码的 .pyc 模块也得留着；只有 __pycache__ 这种能重建的缓存不带。
        root = _release(tmp_path / "src")
        (root / "maafw/MaaAgentClient.dll").write_bytes(b"dll")
        _write(root / "maafw/MaaPiCli.exe", "shell")
        _write(root / "python/Lib/site-packages/maa/bin/MaaFramework.dll", "dll")
        _write(root / "python/Lib/site-packages/numpy/__pycache__/x.pyc", "pyc")
        _write(
            root / "python/Lib/site-packages/pip/_internal/operations/build/wheel.py"
        )
        _write(root / "python/Lib/site-packages/vendor/debug/tool.py")
        _write(root / "python/Lib/site-packages/sealed/core.pyc", "pyc")
        _write(root / "python/Lib/site-packages/setuptools/gui.exe", "exe")

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert {
            "maafw/MaaFramework.dll",
            "maafw/MaaAgentClient.dll",
            "maafw/MaaPiCli.exe",
            "python/python.exe",
            "python/python313.dll",
            "python/Lib/site-packages/maa/bin/MaaFramework.dll",
            "python/Lib/site-packages/pip/_internal/operations/build/wheel.py",
            "python/Lib/site-packages/vendor/debug/tool.py",
            "python/Lib/site-packages/sealed/core.pyc",
            "python/Lib/site-packages/setuptools/gui.exe",
        } <= kept
        assert "python/Lib/site-packages/numpy/__pycache__/x.pyc" not in kept
        assert plan.report()["bundledMaaFWVersion"] == "5.11.1"
        assert plan.report()["bundledPythonVersion"] == "3.13"

    @pytest.mark.parametrize(
        "agent",
        [
            {"child_exec": "./agent/agent.exe"},
            {"type": "custom", "child_exec": "./agent/run.exe"},
        ],
        ids=["native", "custom"],
    )
    def test_non_python_agent_keeps_the_native_runtime(
        self, tmp_path: Path, agent: dict
    ) -> None:
        # 实测 MaaYYs 的 agent.exe 启动时从 <项目>/maafw 加载 MaaFramework，找不到即
        # fatal 退出：非 Python agent 的项目把自带原生库目录原样留下（连里面的 MaaPiCli.exe
        # 一起，原样带走不做分类），只有 __pycache__ 不带。
        root = _release(tmp_path / "src", _interface(agent=agent))
        _write(root / agent["child_exec"], "exe")
        (root / "maafw/MaaAgentServer.dll").write_bytes(b"dll")
        _write(root / "maafw/MaaPiCli.exe", "shell")
        _write(root / "maafw/__pycache__/x.pyc", "pyc")

        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}
        copy = tmp_path / "copy"
        materialize_projection(plan, copy)

        assert {
            "maafw/MaaFramework.dll",
            "maafw/MaaAgentServer.dll",
            "maafw/MaaPiCli.exe",
        } <= kept
        assert "maafw/__pycache__/x.pyc" not in kept
        # runner 与路径模式一样优先用项目自带的那份库，版本也直接从库里读。
        assert probe_bundled_maafw_version(copy) == "5.11.1"

    def test_non_python_agent_without_native_runtime_is_only_a_warning(
        self, tmp_path: Path
    ) -> None:
        root = _release(
            tmp_path / "src", _interface(agent={"child_exec": "./agent/agent.exe"})
        )
        _write(root / "agent/agent.exe", "exe")
        shutil.rmtree(root / "maafw")

        plan = build_projection_plan(root)

        assert any("原生库目录" in warning for warning in plan.rules.warnings)

    def test_update_package_lands_native_runtime_for_non_python_agent(
        self, tmp_path: Path
    ) -> None:
        interface = _interface(agent={"child_exec": "./agent/agent.exe"})
        root = _release(tmp_path / "src", interface)
        _write(root / "agent/agent.exe", "exe")
        copy = tmp_path / "copy"
        materialize_projection(build_projection_plan(root), copy)
        package = tmp_path / "v1.1.0.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "interface.json",
                _interface(version="v1.1.0", agent={"child_exec": "./agent/agent.exe"}),
            )
            archive.writestr("agent/agent.exe", "exe2")
            archive.writestr("maafw/MaaFramework.dll", _bundled_dll("v5.12.3"))
            archive.writestr("maafw/MaaAgentServer.dll", "dll2")
            archive.writestr("MFW.exe", "shell")

        apply_package_transaction(
            copy,
            package,
            operation_root=tmp_path / "operations",
            projection=True,
        )

        assert (copy / "maafw/MaaAgentServer.dll").read_text(encoding="utf-8") == "dll2"
        assert not (copy / "MFW.exe").exists()
        assert probe_bundled_maafw_version(copy) == "5.12.3"

    def test_images_referenced_by_welcome_are_kept(self, tmp_path: Path) -> None:
        # 说明页按项目根取图；先按 README 所在目录解析，再退到项目根，远程与缺失的跳过。
        interface = _interface(welcome="docs/README.md")
        root = _release(tmp_path / "src", interface)
        _write(
            root / "docs/README.md",
            '# hi\n![a](img/a.png)\n<img src="../assets/b.png">\n'
            "![r](https://x/y.png)\n![m](img/missing.png)\n![root](assets/c.png)\n",
        )
        _write(root / "docs/img/a.png", "png")
        _write(root / "assets/b.png", "png")
        _write(root / "assets/c.png", "png")
        _write(root / "assets/unrelated.png", "png")

        kept = {path.as_posix() for path in build_projection_plan(root).copied_files}

        assert {
            "docs/README.md",
            "docs/img/a.png",
            "assets/b.png",
            "assets/c.png",
        } <= kept
        # 未声明但很小的 assets/ 整体留下。
        assert "assets/unrelated.png" in kept

    def test_missing_interpreter_is_a_warning_not_an_error(
        self, tmp_path: Path
    ) -> None:
        # 声明了自带 Python 但包里没发（靠安装脚本事后下载的那种）：planner 落到隔离 venv
        # 兜底，不是发行包不合规。
        root = _release(tmp_path / "src")
        shutil.rmtree(root / "python")

        plan = build_projection_plan(root)

        assert any("隔离 venv" in warning for warning in plan.rules.warnings)
        assert plan.rules.agents[0]["classification"] == "python"
        assert plan.report()["bundledPythonVersion"] == ""

    def test_report_numbers_come_from_the_scan(self, tmp_path: Path) -> None:
        plan = build_projection_plan(_release(tmp_path / "src"))
        report = plan.report()

        assert report["sourceSizeBytes"] > report["payloadSizeBytes"] > 0
        assert (
            report["savedBytes"]
            == report["sourceSizeBytes"] - report["payloadSizeBytes"]
        )
        assert report["excludedCount"] == len(plan.excluded_reasons)
        assert report["shellFamilies"] == ["MFW"]
        assert report["conservative"] is False

    def test_missing_declared_resource_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "src"
        _write(
            root / "interface.json",
            _interface(resource=[{"name": "x", "path": "./nowhere"}]),
        )
        with pytest.raises(ProjectionError, match="nowhere"):
            build_projection_plan(root)

    def test_imports_are_followed_recursively(self, tmp_path: Path) -> None:
        root = tmp_path / "src"
        _write(
            root / "interface.json",
            _interface(**{"import": ["./tasks/a.json"]}, agent=None),
        )
        _write(
            root / "tasks/a.json",
            json.dumps({"import": ["./tasks/b.json"], "task": []}),
        )
        _write(
            root / "tasks/b.json", json.dumps({"task": [{"name": "B", "entry": "B"}]})
        )
        _write(root / "tasks/unreferenced.json", "{}")
        _write(root / "resource/base/x.json", "{}")

        kept = {path.as_posix() for path in build_projection_plan(root).copied_files}

        assert {"tasks/a.json", "tasks/b.json"} <= kept
        # tasks/ 里没被 import 到的文件也留下：未声明的小目录整个带走。
        assert "tasks/unreferenced.json" in kept

    def test_declared_resource_may_be_named_like_a_shell_dir(
        self, tmp_path: Path
    ) -> None:
        # 显式声明的 resource 目录叫 runtime 也要留；里面的缓存照常剔。
        root = tmp_path / "src"
        _write(
            root / "interface.json",
            _interface(resource=[{"name": "x", "path": "./runtime"}], agent=None),
        )
        _write(root / "runtime/pipeline.json", "{}")
        _write(root / "runtime/__pycache__/x.pyc", "pyc")

        kept = {path.as_posix() for path in build_projection_plan(root).copied_files}

        assert "runtime/pipeline.json" in kept
        assert "runtime/__pycache__/x.pyc" not in kept

    def test_opaque_agent_falls_back_to_conservative_mode(self, tmp_path: Path) -> None:
        root = _release(
            tmp_path / "src",
            _interface(agent={"type": "custom", "child_exec": "run.bat"}),
        )
        _write(root / "run.bat", "@echo")
        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}

        assert plan.rules.conservative is True
        assert "README.md" in kept  # 保守模式保留整棵根……
        assert "MFW.exe" not in kept  # ……但分类表命中的外壳仍然不要
        assert "python/python.exe" not in kept


class TestAssetsLayout:
    def test_assets_layout_is_promoted_on_materialize(self, tmp_path: Path) -> None:
        root = tmp_path / "src"
        _write(root / "assets/interface.json", _interface(agent=None))
        _write(root / "assets/resource/base/x.json", "{}")
        _write(root / "README.md", "repo readme")
        _write(root / ".github/workflows/ci.yml", "ci")

        plan = build_projection_plan(root)
        materialize_projection(plan, tmp_path / "out")

        assert (tmp_path / "out/interface.json").is_file()
        assert (tmp_path / "out/resource/base/x.json").is_file()
        assert not (tmp_path / "out/assets").exists()
        assert not (tmp_path / "out/README.md").exists()

    def test_declared_path_outside_assets_is_rejected(self, tmp_path: Path) -> None:
        # 不改写 interface JSON：提升后 ../agent 会指向不存在的位置，直接拒绝。
        root = tmp_path / "src"
        _write(
            root / "assets/interface.json",
            _interface(
                agent={"child_exec": "python", "child_args": ["../agent/main.py"]}
            ),
        )
        _write(root / "assets/resource/base/x.json", "{}")
        _write(root / "agent/main.py", "")
        with pytest.raises(ProjectionError, match="之外"):
            build_projection_plan(root)


class TestAgentArgEdges:
    def test_slash_args_that_are_not_files_do_not_fail_import(
        self, tmp_path: Path
    ) -> None:
        # ``cmd /c``、``--opt=a/b`` 这类参数带斜杠、但不是项目文件：只提醒，不拦导入。
        root = _release(
            tmp_path / "src",
            _interface(
                agent={
                    "child_exec": "./python/python.exe",
                    "child_args": [
                        "/c",
                        "--opt=a/b",
                        "C:/absolute/x",
                        "./agent/main.py",
                    ],
                }
            ),
        )
        plan = build_projection_plan(root)
        kept = {path.as_posix() for path in plan.copied_files}
        assert "agent/main.py" in kept
        assert sum("按普通参数原样保留" in w for w in plan.rules.warnings) >= 1

    def test_missing_script_arg_still_fails_strict_import(self, tmp_path: Path) -> None:
        # 带脚本后缀的参数就是入口文件，缺了必然跑不起来，照旧拒绝。
        root = _release(
            tmp_path / "src",
            _interface(
                agent={
                    "child_exec": "./python/python.exe",
                    "child_args": ["./agent/nope.py"],
                }
            ),
        )
        with pytest.raises(ProjectionError, match="不存在"):
            build_projection_plan(root)

    @pytest.mark.skipif(os.name != "nt", reason="junction 只有 Windows 有")
    def test_junction_is_refused_like_a_symlink(self, tmp_path: Path) -> None:
        import subprocess

        root = _release(tmp_path / "src")
        link = root / "resource" / "base" / "loop"
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(root / "resource")],
            capture_output=True,
            check=True,
        )
        assert link.is_junction()
        with pytest.raises(ProjectionError, match="符号链接"):
            build_projection_plan(root)


class TestMaterialize:
    def test_copies_kept_files_byte_identical(self, tmp_path: Path) -> None:
        source = _release(tmp_path / "src")
        plan = build_projection_plan(source)
        seen: list[tuple[int, int]] = []
        materialize_projection(
            plan, tmp_path / "out", progress=lambda i, n: seen.append((i, n))
        )

        assert (tmp_path / "out/interface.json").read_bytes() == (
            source / "interface.json"
        ).read_bytes()
        assert (tmp_path / "out/resource/base/image/x.png").read_text(
            encoding="utf-8"
        ) == "png"
        assert not (tmp_path / "out/MFW.exe").exists()
        assert not (tmp_path / "out/libs").exists()
        # 自带解释器原样带走。
        assert (tmp_path / "out/python/python.exe").is_file()
        assert seen[-1] == (len(plan.copied_files), len(plan.copied_files))


class TestBundledRuntimeKept:
    """项目自带的原生库与解释器原样进副本；运行时读的就是目录里的东西，没有第二份真相。"""

    def test_materialized_copy_keeps_runtime_and_interpreter(
        self, tmp_path: Path
    ) -> None:
        source = _release(tmp_path / "src")
        plan = build_projection_plan(source)
        copy = tmp_path / "copy"

        materialize_projection(plan, copy)

        assert (copy / "maafw/MaaFramework.dll").read_bytes() == _bundled_dll("v5.11.1")
        assert (copy / "python/python.exe").is_file()
        assert (copy / "python/python313.dll").is_file()
        assert not any(name.startswith(".auto_mas") for name in os.listdir(copy))
        # runner 侧所有钉版本的入口都从目录里的库读，与路径模式同一条路。
        assert probe_bundled_maafw_version(copy) == "5.11.1"
        assert resolve_project_maafw_requirement(copy) == "maafw==5.11.1"
        assert pin_agent_maafw_requirement(copy, ["MaaFw", "json5"]) == [
            "maafw==5.11.1",
            "json5",
        ]

    def test_source_without_native_runtime_reports_nothing(
        self, tmp_path: Path
    ) -> None:
        source = _release(tmp_path / "src")
        shutil.rmtree(source / "maafw")
        plan = build_projection_plan(source)
        copy = tmp_path / "copy"

        materialize_projection(plan, copy)

        assert plan.report()["bundledMaaFWVersion"] == ""
        assert probe_bundled_maafw_version(copy) is None

    def test_update_package_replaces_runtime_and_interpreter(
        self, tmp_path: Path
    ) -> None:
        # 全量包带来新的原生库与解释器：照常落地，版本从新库里读。
        source = _release(tmp_path / "src")
        copy = tmp_path / "copy"
        materialize_projection(build_projection_plan(source), copy)
        package = tmp_path / "v1.1.0.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("interface.json", _interface(version="v1.1.0"))
            archive.writestr("resource/base/pipeline/a.json", '{"A": {"v": 2}}')
            archive.writestr("agent/main.py", "print('hi')")
            archive.writestr("python/python.exe", "exe2")
            archive.writestr("python/python312.dll", "dll")
            archive.writestr("maafw/MaaFramework.dll", _bundled_dll("v5.12.3"))
            archive.writestr("MFW.exe", "shell")

        result = apply_package_transaction(
            copy,
            package,
            operation_root=tmp_path / "operations",
            projection=True,
        )

        assert result.get("applied") is not False
        assert (copy / "python/python.exe").read_text(encoding="utf-8") == "exe2"
        assert (copy / "python/python312.dll").is_file()
        assert not (copy / "MFW.exe").exists()
        assert probe_bundled_maafw_version(copy) == "5.12.3"
        manifest_path = next(
            (tmp_path / "maafw_project_state").rglob("resource-manifest.json")
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "maafw/MaaFramework.dll" in manifest["files"]
        assert "MFW.exe" not in manifest["files"]

    def test_package_without_runtime_leaves_the_copy_runtime_alone(
        self, tmp_path: Path
    ) -> None:
        # 差量包 / 不带运行时的包：副本里的原生库与解释器原样留着。
        source = _release(tmp_path / "src")
        copy = tmp_path / "copy"
        materialize_projection(build_projection_plan(source), copy)
        for version in ("v1.1.0", "v1.2.0"):
            package = tmp_path / f"{version}.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("interface.json", _interface(version=version))
                archive.writestr(
                    "resource/base/pipeline/a.json", f'{{"A": "{version}"}}'
                )
                archive.writestr("agent/main.py", "print('hi')")
            apply_package_transaction(
                copy,
                package,
                operation_root=tmp_path / "operations",
                projection=True,
            )

        assert probe_bundled_maafw_version(copy) == "5.11.1"
        assert (copy / "python/python313.dll").is_file()


class TestPackageRules:
    def _project(self, tmp_path: Path) -> Path:
        project = tmp_path / "project"
        _write(project / "interface.json", _interface(agent=None))
        _write(project / "resource/base/pipeline/a.json", '{"A": {}}')
        return project

    def test_delta_without_interface_uses_the_project_whitelist(
        self, tmp_path: Path
    ) -> None:
        project = self._project(tmp_path)
        payload = tmp_path / "payload"
        _write(payload / "resource/base/pipeline/a.json", '{"A": {"v": 2}}')
        _write(payload / "libs/Avalonia.dll", "dll")
        _write(payload / "python/python.exe", "exe")
        rules = package_projection_rules(payload, project)

        kept, dropped = filter_package_entries(
            rules,
            [
                "resource/base/pipeline/a.json",
                "libs/Avalonia.dll",
                "python/python.exe",
                "MFW.exe",
            ],
        )

        assert kept == {"resource/base/pipeline/a.json"}
        assert dropped["python/python.exe"] == "embedded-python"
        assert dropped["MFW.exe"] == "ui-shell"
        assert dropped["libs/Avalonia.dll"] == "not-required-by-runtime-projection"

    def test_delta_with_new_interface_admits_the_newly_declared_directory(
        self, tmp_path: Path
    ) -> None:
        # 新版本新增的资源目录在包里就是新的，不查存在性。
        project = self._project(tmp_path)
        payload = tmp_path / "payload"
        _write(
            payload / "interface.json",
            _interface(
                agent=None,
                resource=[
                    {"name": "x", "path": ["./resource/base", "./resource/extra"]}
                ],
            ),
        )
        _write(payload / "resource/extra/y.json", "{}")
        rules = package_projection_rules(payload, project)

        kept, _ = filter_package_entries(
            rules, ["interface.json", "resource/extra/y.json"]
        )

        assert kept == {"interface.json", "resource/extra/y.json"}

    def test_assets_layout_package_is_refused(self, tmp_path: Path) -> None:
        project = self._project(tmp_path)
        payload = tmp_path / "payload"
        _write(payload / "assets/interface.json", _interface(agent=None))
        _write(payload / "assets/resource/base/x.json", "{}")
        with pytest.raises(ProjectionError, match="assets"):
            package_projection_rules(payload, project)


class TestApplyWithProjection:
    """全量包经过投影落地：副本只多白名单内的文件，清单也只记这些。"""

    def _package(self, tmp_path: Path, version: str) -> Path:
        package = tmp_path / f"{version}.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("interface.json", _interface(version=version, agent=None))
            archive.writestr("resource/base/pipeline/a.json", '{"A": {"v": 2}}')
            archive.writestr("resource/base/pipeline/new.json", '{"N": {}}')
            archive.writestr("MFW.exe", "shell")
            archive.writestr("libs/Avalonia.dll", "dll")
            archive.writestr("python/python.exe", "exe")
            archive.writestr("README.md", "readme")
        return package

    def test_full_package_lands_slim(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        _write(project / "interface.json", _interface(version="v1.0.0", agent=None))
        _write(project / "resource/base/pipeline/a.json", '{"A": {}}')

        result = apply_package_transaction(
            project,
            self._package(tmp_path, "v1.1.0"),
            operation_root=tmp_path / "operations",
            projection=True,
        )

        assert result.get("applied") is not False
        assert (project / "resource/base/pipeline/new.json").is_file()
        assert json.loads(
            (project / "resource/base/pipeline/a.json").read_text(encoding="utf-8")
        ) == {"A": {"v": 2}}
        for junk in ("MFW.exe", "libs", "python"):
            assert not (project / junk).exists(), junk
        assert (project / "README.md").is_file()
        # 更新器的清单在 operation_root 旁边的 maafw_project_state/<hash>/ 下。
        manifest_path = next(
            (tmp_path / "maafw_project_state").rglob("resource-manifest.json")
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert set(manifest["files"]) == {
            "interface.json",
            "resource/base/pipeline/a.json",
            "resource/base/pipeline/new.json",
            "README.md",
        }

    def test_without_projection_the_same_package_lands_in_full(
        self, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        _write(project / "interface.json", _interface(version="v1.0.0", agent=None))
        _write(project / "resource/base/pipeline/a.json", '{"A": {}}')

        apply_package_transaction(
            project,
            self._package(tmp_path, "v1.1.0"),
            operation_root=tmp_path / "operations",
        )

        assert (project / "MFW.exe").is_file()
        assert (project / "python/python.exe").is_file()


class TestClassification:
    @pytest.mark.parametrize(
        ("path", "reason"),
        [
            ("MFW.exe", "ui-shell"),
            ("MFAAvalonia.dll", "ui-shell"),
            ("libs/MaaFramework.dll", "embedded-runtime"),
            ("python/python.exe", "embedded-python"),
            ("resource/x.pyc", "cache-or-temporary"),
            ("Updater.exe", "ui-or-updater-shell"),
            ("resource/base/pipeline/a.json", None),
        ],
    )
    def test_exclusion_reason_table(self, path: str, reason: str | None) -> None:
        assert exclusion_reason(Path(path)) == reason

    @pytest.mark.parametrize(
        ("declared", "exec_", "args", "expected"),
        [
            ("", "./python/python.exe", ["./agent/main.py"], ("python", False)),
            ("", "python", ["-u", "main.py"], ("python", False)),
            ("", "node", ["agent.js"], ("javascript", False)),
            ("", "./agent/MaaEnd.exe", [], ("native", False)),
            ("custom", "run.bat", [], ("custom", True)),
            ("", "cmd", ["/c", "x"], ("command", True)),
            ("", "something", [], ("external", True)),
            ("", "", [], ("opaque", True)),
        ],
    )
    def test_classify_agent(
        self, declared: str, exec_: str, args: list[str], expected: tuple[str, bool]
    ) -> None:
        assert classify_agent(declared, exec_, args) == expected

    def test_jsonc_interface_is_accepted(self, tmp_path: Path) -> None:
        root = tmp_path / "src"
        _write(
            root / "interface.json",
            '{\n  // 注释\n  "name": "Demo", "version": "v1",\n  "resource": [{"name": "x", "path": "./resource"}],\n}',
        )
        _write(root / "resource/a.json", "{}")

        rules = build_projection_rules(root)

        assert Path("resource") in rules.targets
