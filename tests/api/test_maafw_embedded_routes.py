"""MFW 内嵌四条路由与「按脚本解析有效根」的路由级翻译回归。

只钉 API 层自己的责任：请求怎么变成对服务层的调用、写回配置的形状、失败时配置与
副本是否原样不动、更新入口是否把 ``projection`` 开关传下去。投影本身的规则在
``tests/task/test_maafw_projection.py``，副本服务层在 ``test_maafw_embedded_project.py``。
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.api import scripts
from app.models.schema import (
    MaaFWEmbeddedIn,
    MaaFWEmbeddedReimportIn,
    MaaFWInterfacePreviewIn,
    MaaFWProjectUpdateIn,
)

SCRIPT_ID = "3bc42771-7d59-49fb-99b4-8c86202907b0"


class FakeScriptConfig:
    """只实现路由用到的 get()；update_script 的写入通过 apply() 回灌进来。"""

    is_locked = False

    def __init__(self, path: str = "", enabled: bool = False) -> None:
        self.values: dict[tuple[str, str], Any] = {
            ("Info", "Path"): path,
            ("Embedded", "Enabled"): enabled,
            ("Embedded", "Report"): "{ }",
            ("Embedded", "SourceVersion"): "",
            ("Embedded", "ImportedAt"): "",
        }

    def get(self, group: str, name: str) -> Any:
        return self.values.get((group, name), "")

    def apply(self, update: dict[str, dict[str, Any]]) -> None:
        for group, items in update.items():
            for name, value in items.items():
                self.values[(group, name)] = value


def _write(path: Path, text: str) -> None:
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
    _write(root / "MXU.exe", "shell")
    return root


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """副本落到 tmp 下的 data/maafw_projects/，配置读写全走内存里的假对象。"""

    monkeypatch.chdir(tmp_path)
    fake = FakeScriptConfig()
    writes: list[dict[str, Any]] = []

    async def update_script(script_id: str, update: dict[str, Any]) -> None:
        assert script_id == SCRIPT_ID
        writes.append(update)
        fake.apply(update)

    with (
        patch.object(scripts, "_maafw_script_config", lambda script_id: fake),
        patch.object(
            scripts.Config, "update_script", AsyncMock(side_effect=update_script)
        ),
    ):
        yield SimpleNamespace(
            tmp=tmp_path,
            config=fake,
            writes=writes,
            copy_dir=tmp_path / "data" / "maafw_projects" / SCRIPT_ID,
        )


class TestEnable:
    @pytest.mark.asyncio
    async def test_enable_projects_info_path_and_writes_the_report(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})

        out = await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        assert out.code == 200, out.message
        assert out.data is not None and out.data.enabled is True
        assert out.data.copyHealthy is True
        assert out.data.report is not None
        assert out.data.report.shellFamilies == ["MXU"]
        assert "省下" in out.message and "原目录未改动" in out.message
        # 副本是瘦的，来源没动，Info.Path 还是来源。
        assert (env.copy_dir / "interface.json").is_file()
        assert not (env.copy_dir / "MXU.exe").exists()
        assert (source / "MXU.exe").is_file()
        assert env.config.get("Info", "Path") == str(source)
        # 写回的是 JSON 文本（JSONValidator 在 dev 上不收 dict）。
        assert env.config.get("Embedded", "Enabled") is True
        assert isinstance(env.config.get("Embedded", "Report"), str)
        assert json.loads(env.config.get("Embedded", "Report"))["shellFamilies"] == [
            "MXU"
        ]
        assert env.config.get("Embedded", "SourceVersion") == "v1.0.0"

    @pytest.mark.asyncio
    async def test_enable_without_a_path_is_rejected(self, env) -> None:
        out = await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))
        assert out.code == 400
        assert env.writes == []

    @pytest.mark.asyncio
    async def test_enable_failure_leaves_config_and_disk_untouched(self, env) -> None:
        broken = env.tmp / "broken"
        _write(
            broken / "interface.json",
            json.dumps({"resource": [{"name": "x", "path": "./nowhere"}]}),
        )
        env.config.apply({"Info": {"Path": str(broken)}})

        out = await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        assert out.code == 400
        assert "nowhere" in out.message
        assert env.config.get("Embedded", "Enabled") is False
        assert env.writes == []
        assert not env.copy_dir.exists()


class TestBusyGuards:
    """运行中不许动副本；副本被更新 / 环境准备占着时也不许换树。"""

    @pytest.mark.asyncio
    async def test_running_script_is_rejected_before_touching_disk(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        env.config.is_locked = True

        for call in (
            lambda: scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID)),
            lambda: scripts.reimport_maafw_embedded(
                MaaFWEmbeddedReimportIn(scriptId=SCRIPT_ID, sourcePath=str(source))
            ),
            lambda: scripts.disable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID)),
        ):
            out = await call()
            assert out.code == 400
            assert "正在运行" in out.message

        assert not env.copy_dir.exists()
        assert env.writes == []

    @pytest.mark.asyncio
    async def test_copy_reserved_by_update_blocks_enable_and_disable(self, env) -> None:
        from app.task.MaaFW.tools.embedded.project_path import (
            release_project_path,
            try_reserve_project_path,
        )

        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        key = await try_reserve_project_path(env.copy_dir)
        try:
            out = await scripts.enable_maafw_embedded(
                MaaFWEmbeddedIn(scriptId=SCRIPT_ID)
            )
            assert out.code == 400 and "稍后重试" in out.message
            assert not env.copy_dir.exists()
            env.config.apply({"Embedded": {"Enabled": True}})
            out = await scripts.disable_maafw_embedded(
                MaaFWEmbeddedIn(scriptId=SCRIPT_ID)
            )
            assert out.code == 409
            assert env.config.get("Embedded", "Enabled") is True
        finally:
            await release_project_path(key)


class TestReimportAndDisable:
    @pytest.mark.asyncio
    async def test_reimport_writes_the_new_source_only_after_success(self, env) -> None:
        old = _source(env.tmp / "old")
        env.config.apply({"Info": {"Path": str(old)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))
        new = _source(env.tmp / "new", "v2.0.0")

        out = await scripts.reimport_maafw_embedded(
            MaaFWEmbeddedReimportIn(scriptId=SCRIPT_ID, sourcePath=str(new))
        )

        assert out.code == 200, out.message
        assert env.config.get("Info", "Path") == str(new)
        assert env.config.get("Embedded", "SourceVersion") == "v2.0.0"
        assert out.data is not None and out.data.sourceVersion == "v2.0.0"

    @pytest.mark.asyncio
    async def test_failed_reimport_keeps_old_source_and_copy(self, env) -> None:
        old = _source(env.tmp / "old")
        env.config.apply({"Info": {"Path": str(old)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))
        before = len(env.writes)

        out = await scripts.reimport_maafw_embedded(
            MaaFWEmbeddedReimportIn(
                scriptId=SCRIPT_ID, sourcePath=str(env.tmp / "missing")
            )
        )

        assert out.code == 400
        assert env.config.get("Info", "Path") == str(old)
        assert len(env.writes) == before
        assert (env.copy_dir / "interface.json").is_file()

    @pytest.mark.asyncio
    async def test_disable_removes_the_copy_and_resets_embedded_keys(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        out = await scripts.disable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        assert out.code == 200
        assert "回到来源目录" in out.message
        assert not env.copy_dir.exists()
        assert env.config.get("Embedded", "Enabled") is False
        assert env.config.get("Embedded", "Report") == "{ }"
        assert env.config.get("Embedded", "SourceVersion") == ""
        # 来源还是来源：退出内嵌不会改 Info.Path。
        assert env.config.get("Info", "Path") == str(source)
        assert out.data is not None and out.data.enabled is False

    @pytest.mark.asyncio
    async def test_disable_warns_when_the_source_is_gone(self, env) -> None:
        env.config.apply(
            {"Info": {"Path": str(env.tmp / "gone")}, "Embedded": {"Enabled": True}}
        )

        out = await scripts.disable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        assert out.code == 200
        assert "来源目录已不存在" in out.message

    @pytest.mark.asyncio
    async def test_status_reports_both_sides(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        out = await scripts.get_maafw_embedded_status(
            MaaFWEmbeddedIn(scriptId=SCRIPT_ID)
        )

        assert out.data is not None
        assert out.data.enabled and out.data.copyHealthy and out.data.sourceExists
        assert out.data.copyPath == str(env.copy_dir)
        assert out.data.sourcePath == str(source)


class TestEffectiveRoot:
    @pytest.mark.asyncio
    async def test_plain_script_resolves_to_info_path(self, env) -> None:
        env.config.apply({"Info": {"Path": str(env.tmp / "plain")}})

        root, error = await scripts._maafw_effective_root(SCRIPT_ID, "")

        assert error == ""
        assert root == (env.tmp / "plain").resolve()

    @pytest.mark.asyncio
    async def test_embedded_script_resolves_to_the_copy(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))

        root, error = await scripts._maafw_effective_root(SCRIPT_ID, str(source))

        assert error == ""
        assert root == env.copy_dir.resolve()

    @pytest.mark.asyncio
    async def test_missing_copy_is_rebuilt_and_report_written_back(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}, "Embedded": {"Enabled": True}})
        assert not env.copy_dir.exists()

        root, error = await scripts._maafw_effective_root(SCRIPT_ID, "")

        assert error == ""
        assert root == env.copy_dir.resolve()
        assert (env.copy_dir / "interface.json").is_file()
        assert json.loads(env.config.get("Embedded", "Report"))["shellFamilies"] == [
            "MXU"
        ]
        # 自修复不会碰 Enabled，也不会碰 Info.Path。
        assert env.config.get("Embedded", "Enabled") is True
        assert env.config.get("Info", "Path") == str(source)

    @pytest.mark.asyncio
    async def test_missing_copy_without_source_is_an_error_not_a_crash(
        self, env
    ) -> None:
        env.config.apply(
            {"Info": {"Path": str(env.tmp / "gone")}, "Embedded": {"Enabled": True}}
        )

        root, error = await scripts._maafw_effective_root(SCRIPT_ID, "")

        assert root is None
        assert "来源目录已不存在" in error

    @pytest.mark.asyncio
    async def test_no_script_id_falls_back_to_the_request_path(self, env) -> None:
        root, error = await scripts._maafw_effective_root(None, str(env.tmp / "raw"))
        assert (root, error) == ((env.tmp / "raw").resolve(), "")
        root, error = await scripts._maafw_effective_root(None, "  ")
        assert root is None and error

    @pytest.mark.asyncio
    async def test_preview_prefers_script_id_over_path(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))
        seen: list[Path] = []

        def fake_load(root: Path):
            seen.append(root)
            raise scripts.MaaFWInterfaceLoadError("stop here")

        with patch.object(scripts, "load_interface_model_cached", fake_load):
            out = await scripts.preview_maafw_interface(
                MaaFWInterfacePreviewIn(path=str(source), scriptId=SCRIPT_ID)
            )

        assert out.code == 400
        assert seen == [env.copy_dir.resolve()]


class TestUpdateRoute:
    @pytest.mark.asyncio
    async def test_apply_on_embedded_script_runs_on_the_copy_with_projection(
        self, env
    ) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        await scripts.enable_maafw_embedded(MaaFWEmbeddedIn(scriptId=SCRIPT_ID))
        update = AsyncMock(return_value=SimpleNamespace(message="done", updated=False))

        with (
            patch.object(
                scripts,
                "load_interface_model_cached",
                lambda root: SimpleNamespace(version="v1.0.0"),
            ),
            patch.object(scripts, "update_maafw_project_if_needed", update),
        ):
            out = await scripts.update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=SCRIPT_ID, action="apply")
            )

        assert out.code == 200, out.message
        update.assert_awaited_once()
        args, kwargs = update.await_args
        assert args[0] == env.copy_dir.resolve()
        assert kwargs["projection"] is True
        # 副本里没有 MXU.exe 可扫，外壳提示必须从报告来。
        assert kwargs["source_config"]["project_shell_hint"] == "MXU"

    @pytest.mark.asyncio
    async def test_apply_on_plain_script_keeps_projection_off(self, env) -> None:
        source = _source(env.tmp / "src")
        env.config.apply({"Info": {"Path": str(source)}})
        update = AsyncMock(return_value=SimpleNamespace(message="done", updated=False))

        with (
            patch.object(
                scripts,
                "load_interface_model_cached",
                lambda root: SimpleNamespace(version="v1.0.0"),
            ),
            patch.object(scripts, "update_maafw_project_if_needed", update),
        ):
            out = await scripts.update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=SCRIPT_ID, action="apply")
            )

        assert out.code == 200, out.message
        args, kwargs = update.await_args
        assert args[0] == source.resolve()
        assert kwargs["projection"] is False
        # 普通模式还是扫目录：MXU.exe 在，提示也应是 MXU。
        assert kwargs["source_config"]["project_shell_hint"] == "MXU"
