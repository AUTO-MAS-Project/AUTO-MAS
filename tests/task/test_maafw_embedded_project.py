"""MFW 内嵌副本服务层的纯逻辑回归。

副本路径由脚本 ID 推出、不进配置；``Info.Path`` 永远是来源目录。这里钉的是：
有效根在两种模式下从哪来、导入是"先 staging 再原子换入"且失败不动旧副本、副本缺失
时的自修复口径、外壳提示只能从报告取。全部在临时目录里，不碰真实发行包。
"""

import asyncio
import json
import os
import stat
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.task import ScriptItem, TaskItem
from app.task.MaaFW import embedded_manager
from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    apply_package_transaction,
    has_trusted_update_baseline,
)
from app.task.MaaFW.tools.embedded.embedded_project import (
    EmbeddedProjectError,
    discard_copy_update_baseline,
    embedded_project_dir,
    embedded_status,
    ensure_embedded_copy,
    import_embedded_project,
    is_embedded,
    remove_tree,
    resolve_maafw_project_root,
    shell_hint_from_report,
)
from app.task.MaaFW.tools.embedded.update_credentials import MaaFWUpdateCredentials

SCRIPT_ID = "3bc42771-7d59-49fb-99b4-8c86202907b0"


class FakeConfig:
    def __init__(
        self, path: str = "", enabled: bool = False, report: object = "{ }"
    ) -> None:
        self.values = {
            ("Info", "Path"): path,
            ("Embedded", "Enabled"): enabled,
            ("Embedded", "Report"): report,
            ("Embedded", "SourceVersion"): "",
            ("Embedded", "ImportedAt"): "",
        }

    def get(self, group: str, name: str):
        return self.values[(group, name)]


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source(root: Path, version: str = "v1.0.0") -> Path:
    _write(
        root / "interface.json",
        json.dumps(
            {
                "name": "Demo",
                "version": version,
                "resource": [{"name": "x", "path": "./resource/base"}],
            }
        ),
    )
    _write(root / "resource/base/a.json", "{}")
    _write(root / "MFW.exe", "shell")
    _write(root / "python/python.exe", "exe")
    return root


class TestProjectRoot:
    def test_copy_dir_is_derived_from_the_script_uuid(self, tmp_path: Path) -> None:
        assert embedded_project_dir(SCRIPT_ID, tmp_path) == (
            tmp_path / "data" / "maafw_projects" / SCRIPT_ID
        )

    def test_copy_dir_refuses_non_uuid_ids(self, tmp_path: Path) -> None:
        # 拼进路径里的必须是脚本 ID，不能是别的什么。
        with pytest.raises(EmbeddedProjectError):
            embedded_project_dir("../etc", tmp_path)

    def test_effective_root_follows_the_mode(self, tmp_path: Path) -> None:
        assert resolve_maafw_project_root(
            SCRIPT_ID, FakeConfig(r"D:\x"), tmp_path
        ) == Path(r"D:\x")
        assert resolve_maafw_project_root(
            SCRIPT_ID, FakeConfig(r"D:\x", enabled=True), tmp_path
        ) == embedded_project_dir(SCRIPT_ID, tmp_path)

    def test_is_embedded_tolerates_old_config_objects(self) -> None:
        class Ancient:
            def get(self, group, name):
                raise AttributeError("配置项不存在")

        assert is_embedded(Ancient()) is False


class TestImport:
    def test_import_builds_a_slim_copy_and_returns_the_report(
        self, tmp_path: Path
    ) -> None:
        source = _source(tmp_path / "src")

        imported = import_embedded_project(SCRIPT_ID, source, base=tmp_path)
        copy_dir = embedded_project_dir(SCRIPT_ID, tmp_path)

        assert (copy_dir / "interface.json").is_file()
        assert (copy_dir / "resource/base/a.json").is_file()
        assert not (copy_dir / "MFW.exe").exists()
        assert not (copy_dir / "python").exists()
        assert imported["sourceVersion"] == "v1.0.0"
        assert imported["report"]["shellFamilies"] == ["MFW"]
        assert imported["report"]["sourcePath"] == str(source.resolve())
        # 来源一个字节不动。
        assert (source / "MFW.exe").is_file()
        # staging 不留东西。
        assert not any((tmp_path / "data/maafw_projects/.staging").iterdir())

    def test_reimport_replaces_the_copy_atomically(self, tmp_path: Path) -> None:
        import_embedded_project(SCRIPT_ID, _source(tmp_path / "v1"), base=tmp_path)
        copy_dir = embedded_project_dir(SCRIPT_ID, tmp_path)
        _write(copy_dir / "stale.json", "left over")

        import_embedded_project(
            SCRIPT_ID, _source(tmp_path / "v2", "v2.0.0"), base=tmp_path
        )

        assert (
            json.loads((copy_dir / "interface.json").read_text(encoding="utf-8"))[
                "version"
            ]
            == "v2.0.0"
        )
        assert not (copy_dir / "stale.json").exists()

    def test_failed_import_leaves_the_old_copy_untouched(self, tmp_path: Path) -> None:
        import_embedded_project(SCRIPT_ID, _source(tmp_path / "v1"), base=tmp_path)
        broken = tmp_path / "broken"
        _write(
            broken / "interface.json",
            json.dumps({"resource": [{"name": "x", "path": "./nowhere"}]}),
        )

        with pytest.raises(EmbeddedProjectError, match="nowhere"):
            import_embedded_project(SCRIPT_ID, broken, base=tmp_path)

        copy_dir = embedded_project_dir(SCRIPT_ID, tmp_path)
        assert (
            json.loads((copy_dir / "interface.json").read_text(encoding="utf-8"))[
                "version"
            ]
            == "v1.0.0"
        )
        assert not any((tmp_path / "data/maafw_projects/.staging").iterdir())

    def test_source_must_be_an_existing_absolute_directory(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(EmbeddedProjectError):
            import_embedded_project(SCRIPT_ID, "relative/path", base=tmp_path)
        with pytest.raises(EmbeddedProjectError):
            import_embedded_project(SCRIPT_ID, tmp_path / "missing", base=tmp_path)

    def test_source_cannot_be_the_copy_itself(self, tmp_path: Path) -> None:
        import_embedded_project(SCRIPT_ID, _source(tmp_path / "v1"), base=tmp_path)
        with pytest.raises(EmbeddedProjectError, match="自己"):
            import_embedded_project(
                SCRIPT_ID, embedded_project_dir(SCRIPT_ID, tmp_path), base=tmp_path
            )


class TestUpdateBaseline:
    """副本整棵换掉后，更新器上一次记的清单必须跟着作废。"""

    def _package(self, tmp_path: Path, version: str) -> Path:
        import zipfile

        package = tmp_path / f"{version}.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "interface.json",
                json.dumps(
                    {
                        "name": "Demo",
                        "version": version,
                        "resource": [{"name": "x", "path": "./resource/base"}],
                    }
                ),
            )
            archive.writestr("resource/base/a.json", '{"v": 2}')
        return package

    def test_reimport_discards_the_recorded_baseline(self, tmp_path: Path) -> None:
        source = _source(tmp_path / "src")
        import_embedded_project(SCRIPT_ID, source, base=tmp_path)
        copy = embedded_project_dir(SCRIPT_ID, tmp_path)
        operation_root = tmp_path / "data" / "maafw_update_operations"
        apply_package_transaction(
            copy,
            self._package(tmp_path, "v1.1.0"),
            operation_root=operation_root,
            projection=True,
        )
        assert has_trusted_update_baseline(copy, operation_root=operation_root)

        # 用户手动更新了来源，点「重新导入」：树换了，清单不能留。
        import_embedded_project(
            SCRIPT_ID, _source(tmp_path / "v2", "v2.0.0"), base=tmp_path
        )

        assert not has_trusted_update_baseline(copy, operation_root=operation_root)
        # 再来一个包要能正常落地，而不是「文件被本地修改」。
        result = apply_package_transaction(
            copy,
            self._package(tmp_path, "v2.1.0"),
            operation_root=operation_root,
            projection=True,
        )
        assert result.get("applied") is not False

    def test_discard_is_a_no_op_without_a_baseline(self, tmp_path: Path) -> None:
        assert discard_copy_update_baseline(SCRIPT_ID, tmp_path) is False


class _Task(TaskItem):
    async def on_change(self) -> None:
        return None


class TestCheckSelfHeal:
    """check() 的自修复跑在工作线程里；日志回调必须线程安全，否则整个任务崩在第一行。"""

    @pytest.mark.asyncio
    async def test_check_rebuilds_missing_copy_without_touching_the_loop_from_a_thread(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading

        from app.task.MaaFW import embedded_manager

        monkeypatch.chdir(tmp_path)
        source = _source(tmp_path / "src")
        config = MaaFWConfig()
        await config.load(
            {"Info": {"Path": str(source)}, "Embedded": {"Enabled": True}}
        )

        task = _Task(
            mode="AutoProxy",
            task_id="t",
            queue_id=None,
            script_id=SCRIPT_ID,
            user_id=None,
        )
        script_item = ScriptItem(script_id=SCRIPT_ID, name="demo", status="等待")
        task.script_list = [script_item]  # 真实绑定：写 log 会走 schedule_on_change
        manager = embedded_manager.MaaFWEmbeddedManager.__new__(
            embedded_manager.MaaFWEmbeddedManager
        )
        manager.task_info = task
        manager.script_info = script_item
        manager.project_update_logs = []
        manager.script_config = None

        threads: list[str] = []

        def fake_ensure(script_id, script_config, *, base=None, send_log=None):
            threads.append(threading.current_thread().name)
            send_log("[MFW 内嵌] 副本缺失或损坏，正在从来源目录重新导入")
            return import_embedded_project(script_id, str(source), base=base)

        # 一个可运行的用户，让 check() 一路走到运行前自检与 Pass。
        await config.UserData.add(MaaFWUserConfig)
        checked_roots: list[Path] = []

        def fake_self_check(project_path: Path) -> str | None:
            checked_roots.append(project_path)
            return None

        update_script = AsyncMock()
        fake_host = SimpleNamespace(
            ScriptConfig={uuid.UUID(SCRIPT_ID): config}, update_script=update_script
        )
        with (
            patch.object(embedded_manager, "ensure_embedded_copy", fake_ensure),
            patch.object(embedded_manager, "Config", fake_host),
            patch.object(
                embedded_manager, "describe_unusable_runtime", fake_self_check
            ),
        ):
            monkeypatch.setattr(config, "lock", AsyncMock())
            result = await manager.check()

        assert threads and threads[0] != threading.main_thread().name
        assert result == "Pass"
        copy_dir = embedded_project_dir(SCRIPT_ID, tmp_path)
        assert (copy_dir / "interface.json").is_file()
        # 运行前自检看的是副本（运行池版本钉在副本的标记上），不是来源目录。
        assert checked_roots == [copy_dir]
        update_script.assert_awaited_once()
        written = update_script.await_args.args[1]["Embedded"]
        assert json.loads(written["Report"])["shellFamilies"] == ["MFW"]
        # 让 call_soon_threadsafe 排进来的日志写入跑完，日志确实到了 script_info。
        await asyncio.sleep(0)
        assert "重新导入" in script_item.log


class TestSelfHeal:
    def test_healthy_copy_is_left_alone(self, tmp_path: Path) -> None:
        source = _source(tmp_path / "src")
        import_embedded_project(SCRIPT_ID, source, base=tmp_path)
        config = FakeConfig(str(source), enabled=True)

        assert ensure_embedded_copy(SCRIPT_ID, config, base=tmp_path) is None

    def test_missing_copy_is_rebuilt_from_the_source(self, tmp_path: Path) -> None:
        # 复制脚本、手删、迁移磁盘都会走到这里。
        source = _source(tmp_path / "src")
        config = FakeConfig(str(source), enabled=True)
        logs: list[str] = []

        rebuilt = ensure_embedded_copy(
            SCRIPT_ID, config, base=tmp_path, send_log=logs.append
        )

        assert rebuilt is not None and rebuilt["sourceVersion"] == "v1.0.0"
        assert (embedded_project_dir(SCRIPT_ID, tmp_path) / "interface.json").is_file()
        assert any("重新导入" in line for line in logs)

    def test_missing_copy_without_source_is_an_error(self, tmp_path: Path) -> None:
        config = FakeConfig(str(tmp_path / "gone"), enabled=True)
        with pytest.raises(EmbeddedProjectError, match="来源目录已不存在"):
            ensure_embedded_copy(SCRIPT_ID, config, base=tmp_path)

    def test_not_embedded_is_a_no_op(self, tmp_path: Path) -> None:
        assert (
            ensure_embedded_copy(
                SCRIPT_ID, FakeConfig("", enabled=False), base=tmp_path
            )
            is None
        )


class TestStatusAndHints:
    def test_status_reads_report_stored_as_json_text(self, tmp_path: Path) -> None:
        source = _source(tmp_path / "src")
        imported = import_embedded_project(SCRIPT_ID, source, base=tmp_path)
        config = FakeConfig(
            str(source), enabled=True, report=json.dumps(imported["report"])
        )

        status = embedded_status(SCRIPT_ID, config, base=tmp_path)

        assert status["enabled"] is True
        assert status["copyHealthy"] is True
        assert status["sourceExists"] is True
        assert status["report"]["shellFamilies"] == ["MFW"]

    def test_status_degrades_on_bad_report_text(self, tmp_path: Path) -> None:
        status = embedded_status(
            SCRIPT_ID, FakeConfig("", report="not json"), base=tmp_path
        )
        assert status["report"] == {}
        assert status["copyHealthy"] is False

    def test_shell_hint_prefers_the_primary_family(self) -> None:
        # MXU 包里常留着 MaaPiCli，选资产要看主外壳；报告可以是 JSON 文本或已解析对象。
        assert (
            shell_hint_from_report(
                FakeConfig(report={"shellFamilies": ["MaaPiCli", "MXU"]})
            )
            == "MXU"
        )
        assert (
            shell_hint_from_report(
                FakeConfig(report=json.dumps({"shellFamilies": ["MFAAvalonia"]}))
            )
            == "MFAAvalonia"
        )
        assert shell_hint_from_report(FakeConfig(report="{ }")) == ""
        assert shell_hint_from_report(FakeConfig(report="garbage")) == ""


class TestRemoveTree:
    def test_readonly_files_do_not_block_removal(self, tmp_path: Path) -> None:
        # 发行包里的 .git 对象之类是只读的，rmtree 默认会卡在上面。
        victim = tmp_path / "victim"
        _write(victim / "ro.bin", "x")
        os.chmod(victim / "ro.bin", stat.S_IREAD)

        remove_tree(victim)

        assert not victim.exists()

    def test_missing_tree_is_fine(self, tmp_path: Path) -> None:
        remove_tree(tmp_path / "nope")


def test_script_ids_normalize_to_canonical_uuid(tmp_path: Path) -> None:
    raw = uuid.uuid4()
    assert embedded_project_dir(str(raw).upper(), tmp_path).name == str(raw)


class TestManagerWiring:
    """运行时自动更新走 manager：内嵌脚本必须带 projection 与报告里的外壳提示。"""

    @pytest.mark.asyncio
    async def test_runtime_update_passes_projection_and_shell_hint(self) -> None:
        manager = embedded_manager.MaaFWEmbeddedManager.__new__(
            embedded_manager.MaaFWEmbeddedManager
        )
        manager.script_config = FakeConfig(
            r"D:\src",
            enabled=True,
            report=json.dumps({"shellFamilies": ["MFAAvalonia"]}),
        )
        manager.script_info = SimpleNamespace(log="")
        manager.project_update_logs = []
        update = AsyncMock(return_value=SimpleNamespace(message="ok"))
        credentials = MaaFWUpdateCredentials(source="GitHub", cdk="", channel="stable")

        with (
            patch.object(
                embedded_manager.MaaFWEmbeddedManager,
                "_load_interface_model",
                staticmethod(
                    lambda path, *, force_reload=False: SimpleNamespace(version="v1")
                ),
            ),
            patch(
                "app.task.MaaFW.tools.core.automas_maafw_project_update.update_maafw_project_if_needed",
                update,
            ),
        ):
            await manager._invoke_project_update(Path(r"D:\copy"), credentials)

        update.assert_awaited_once()
        args, kwargs = update.await_args
        assert args[0] == Path(r"D:\copy")
        assert kwargs["projection"] is True
        assert kwargs["source_config"]["project_shell_hint"] == "MFAAvalonia"
        assert kwargs["source_config"]["package_source"] == "github_release"

    @pytest.mark.asyncio
    async def test_runtime_update_on_plain_script_keeps_projection_off(self) -> None:
        manager = embedded_manager.MaaFWEmbeddedManager.__new__(
            embedded_manager.MaaFWEmbeddedManager
        )
        manager.script_config = FakeConfig(r"D:\src", enabled=False)
        manager.script_info = SimpleNamespace(log="")
        manager.project_update_logs = []
        update = AsyncMock(return_value=SimpleNamespace(message="ok"))
        credentials = MaaFWUpdateCredentials(
            source="MirrorChyan", cdk="k", channel="beta"
        )

        with (
            patch.object(
                embedded_manager.MaaFWEmbeddedManager,
                "_load_interface_model",
                staticmethod(
                    lambda path, *, force_reload=False: SimpleNamespace(version="v1")
                ),
            ),
            patch(
                "app.task.MaaFW.tools.core.automas_maafw_project_update.update_maafw_project_if_needed",
                update,
            ),
        ):
            await manager._invoke_project_update(Path(r"D:\src"), credentials)

        _args, kwargs = update.await_args
        assert kwargs["projection"] is False
        assert "project_shell_hint" not in kwargs["source_config"]
        assert kwargs["mirror_cdk"] == "k" and kwargs["channel"] == "beta"
