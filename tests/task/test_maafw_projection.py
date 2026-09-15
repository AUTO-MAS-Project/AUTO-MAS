"""按 interface 白名单投影 MaaFW 发行包的纯逻辑回归。

投影是"只拿声明了的"，不是"删掉外壳"。每一条都是写错了不报错、只会让副本多出或
少掉文件的地方：白名单目标的口径（完整 / 保留根 / 豁免根名）、assets 布局的提升、
自带解释器被投影掉时不算错、差量包的叠加视图、以及 ``build_package_plan`` 三张表
一起过滤。夹具全部是临时目录里合成的迷你项目，不碰真实发行包。
"""

import json
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
    _write(root / "python/python312.dll", "dll" * 100)
    _write(root / "MFW.exe", "shell" * 100)
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
        }
        reasons = plan.excluded_reasons
        assert reasons["MFW.exe"] == "ui-shell"
        assert reasons["python/python.exe"] == "embedded-python"
        assert reasons["runtimes/win-x64/native/x.dll"] == "embedded-runtime"
        assert reasons["agent/__pycache__/main.cpython-312.pyc"] == "cache"
        # 声明目录里的缓存也剔，白名单不是免检。
        assert reasons["resource/base/__pycache__/junk.pyc"] == "cache"
        assert reasons["README.md"] == "not-required-by-runtime-projection"

    def test_stripped_interpreter_is_a_warning_not_an_error(
        self, tmp_path: Path
    ) -> None:
        # 自带 Python 被投影掉由 planner 落到隔离 venv 兜底，不是发行包不合规。
        plan = build_projection_plan(_release(tmp_path / "src"))

        assert any("隔离 venv" in warning for warning in plan.rules.warnings)
        assert plan.rules.agents[0]["classification"] == "python"

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
        assert "tasks/unreferenced.json" not in kept

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
        assert not (tmp_path / "out/python").exists()
        assert seen[-1] == (len(plan.copied_files), len(plan.copied_files))


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
        for junk in ("MFW.exe", "libs", "python", "README.md"):
            assert not (project / junk).exists(), junk
        # 更新器的清单在 operation_root 旁边的 maafw_project_state/<hash>/ 下。
        manifest_path = next(
            (tmp_path / "maafw_project_state").rglob("resource-manifest.json")
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert set(manifest["files"]) == {
            "interface.json",
            "resource/base/pipeline/a.json",
            "resource/base/pipeline/new.json",
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
