"""受管文件在本地被改过，不能让项目从此永远更新不了。

更新器给自己铺过的每个文件记 sha256 清单。以前 apply 阶段任一受管文件哈希不符
就 fail-closed 拒装——可 M9A 自带的 agent 每次启动都热更新 ``data/activity/*.json``，
上游一发新版，MAS 每次运行都先下完 210MB 全量包再拒装，项目永远停在旧版，用户
没有任何界面能解开。现在的口径：

- 全量包：记警告、把本地那份留到 ``<state>/local-modified/``，然后照常覆盖；
- 差量包：它要求项目指纹与基线**完全一致**，对不上就整个拒装，所以在带 CDK 向
  Mirror酱 要包之前先比一次指纹，不一致就改要全量包。指纹要 ~2s，只在「确认有新
  版本、且真要从 Mirror酱 下载」那一刻才算，「已是最新」的绝大多数运行不付这笔账。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.task.MaaFW.tools.core.automas_maafw_project_update import updater
from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    LOCAL_MODIFIED_DIR_NAME,
    MANIFEST_NAME,
    _resolve_project_state_dir,
    apply_package_transaction,
    update_baseline_matches_project,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    MaaFWMirrorChyanVersionCheck,
    update_maafw_project_if_needed,
)

ACTIVITY = "data/activity/cn.json"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _interface(version: str) -> str:
    return json.dumps(
        {
            "name": "M9A",
            "version": version,
            "resource": [{"name": "官服", "path": ["./resource/base"]}],
        },
        ensure_ascii=False,
    )


def _package(tmp_path: Path, version: str, activity: str) -> Path:
    package_path = tmp_path / f"{version}.zip"
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.writestr("interface.json", _interface(version))
        archive.writestr("resource/base/pipeline/main.json", '{"main": {}}')
        archive.writestr(ACTIVITY, activity)
    return package_path


def _apply(project: Path, package: Path, tmp_path: Path, logs: list[str]) -> dict:
    return apply_package_transaction(
        project,
        package,
        operation_root=tmp_path / "operations",
        send_log=logs.append,
    )


def _installed_project(tmp_path: Path) -> tuple[Path, list[str]]:
    """先让更新器自己铺一版 v1.0.0，这样就有了清单（受管文件基线）。"""

    project = tmp_path / "project"
    _write(project / "interface.json", _interface("v0.9.0"))
    logs: list[str] = []
    result = _apply(
        project, _package(tmp_path, "v1.0.0", '{"activity": "v1.0.0"}'), tmp_path, logs
    )
    assert result["status"] == "committed"
    logs.clear()
    return project, logs


def _state_dir(project: Path, tmp_path: Path) -> Path:
    return _resolve_project_state_dir(project, tmp_path / "operations")


def test_full_update_overwrites_hot_patched_file_and_keeps_a_copy(
    tmp_path: Path,
) -> None:
    project, logs = _installed_project(tmp_path)
    # 项目自己的 agent 热更新改写了受管文件
    _write(project / ACTIVITY, '{"activity": "hot-patched"}')

    result = _apply(
        project, _package(tmp_path, "v1.1.0", '{"activity": "v1.1.0"}'), tmp_path, logs
    )

    assert result["status"] == "committed", "本地改过受管文件不能再拒装"
    assert (project / ACTIVITY).read_text(encoding="utf-8") == '{"activity": "v1.1.0"}'
    kept = _state_dir(project, tmp_path) / LOCAL_MODIFIED_DIR_NAME / ACTIVITY
    assert kept.read_text(encoding="utf-8") == '{"activity": "hot-patched"}', (
        "覆盖前的本地版本要留档，用户改过的东西得有处可找"
    )
    assert any("受管文件在本地被改过" in line and ACTIVITY in line for line in logs)
    # 清单跟着新内容走：下一次更新不会再把同一文件报成本地改动
    manifest = json.loads(
        (_state_dir(project, tmp_path) / MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert (
        manifest["files"][ACTIVITY]
        == hashlib.sha256(b'{"activity": "v1.1.0"}').hexdigest()
    )


def test_unmodified_project_leaves_no_local_modified_copy(tmp_path: Path) -> None:
    project, logs = _installed_project(tmp_path)

    _apply(
        project, _package(tmp_path, "v1.1.0", '{"activity": "v1.1.0"}'), tmp_path, logs
    )

    assert not (_state_dir(project, tmp_path) / LOCAL_MODIFIED_DIR_NAME).exists()
    assert not any("受管文件在本地被改过" in line for line in logs)


def test_local_modified_dir_only_keeps_the_latest_update(tmp_path: Path) -> None:
    project, logs = _installed_project(tmp_path)
    _write(project / ACTIVITY, '{"activity": "patched-1"}')
    _apply(
        project, _package(tmp_path, "v1.1.0", '{"activity": "v1.1.0"}'), tmp_path, logs
    )
    _write(project / "resource/base/pipeline/main.json", '{"main": "patched"}')

    _apply(
        project, _package(tmp_path, "v1.2.0", '{"activity": "v1.2.0"}'), tmp_path, logs
    )

    keep_dir = _state_dir(project, tmp_path) / LOCAL_MODIFIED_DIR_NAME
    assert (keep_dir / "resource/base/pipeline/main.json").is_file()
    assert not (keep_dir / ACTIVITY).exists(), "留档不是版本库，只保留最近一次"


def test_update_baseline_matches_project_tracks_local_changes(tmp_path: Path) -> None:
    project, _logs = _installed_project(tmp_path)
    operation_root = tmp_path / "operations"

    assert update_baseline_matches_project(project, operation_root=operation_root)

    _write(project / ACTIVITY, '{"activity": "hot-patched"}')
    assert not update_baseline_matches_project(project, operation_root=operation_root)

    assert not update_baseline_matches_project(
        tmp_path / "never-updated", operation_root=operation_root
    ), "没有清单就没有基线"


# ---------------------------------------------------------------------------
# updater：指纹对不上就别去要差量包，而且只在真要差量包时才算指纹
# ---------------------------------------------------------------------------


class _MirrorStub:
    """替身 ``_query_mirrorchyan_latest``：记录每次查询的 prefer_full 与是否带 CDK。"""

    def __init__(self, latest: str) -> None:
        self.latest = latest
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, *_args: Any, **kwargs: Any
    ) -> MaaFWMirrorChyanVersionCheck:
        self.calls.append(
            {
                "cdk": bool(kwargs.get("mirror_cdk")),
                "prefer_full": kwargs["prefer_full"],
            }
        )
        return MaaFWMirrorChyanVersionCheck(
            version_name=self.latest,
            download_url="https://example.invalid/pkg.zip"
            if kwargs.get("mirror_cdk")
            else None,
            cdk_status="valid" if kwargs.get("mirror_cdk") else "absent",
        )


class _FingerprintSpy:
    def __init__(self, matches: bool) -> None:
        self.matches = matches
        self.calls = 0

    def __call__(self, _project_path: Path) -> bool:
        self.calls += 1
        return self.matches


@pytest.fixture
def updater_harness(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    harness: dict[str, Any] = {}
    monkeypatch.setattr(updater, "has_trusted_update_baseline", lambda _p: True)
    monkeypatch.setattr(
        updater, "detect_maafw_project_shell_hint", lambda _p: "MFAAvalonia"
    )

    async def fake_apply(_project_path: Path, cand: Any, **_kwargs: Any) -> dict:
        harness["applied"] = cand
        return {"operationId": "op", "planId": cand.plan_id}

    monkeypatch.setattr(updater, "apply_maafw_project_update", fake_apply)

    def install(latest: str, matches: bool) -> None:
        harness["mirror"] = _MirrorStub(latest)
        harness["fingerprint"] = _FingerprintSpy(matches)
        monkeypatch.setattr(updater, "_query_mirrorchyan_latest", harness["mirror"])
        monkeypatch.setattr(
            updater, "update_baseline_matches_project", harness["fingerprint"]
        )

    harness["install"] = install
    return harness


def _interface_model() -> Any:
    return SimpleNamespace(
        version="v1.0.0", mirrorchyan_rid="M9A", github="MAA1999/M9A"
    )


@pytest.mark.asyncio
async def test_fingerprint_mismatch_with_cdk_requests_full_package(
    tmp_path: Path, updater_harness: dict[str, Any]
) -> None:
    updater_harness["install"]("v1.1.0", matches=False)
    logs: list[str] = []

    await update_maafw_project_if_needed(
        tmp_path,
        _interface_model(),
        source_config={"package_source": "mirrorchyan", "mirror_cdk": "cdk-secret"},
        send_log=logs.append,
    )

    calls = updater_harness["mirror"].calls
    assert [c["cdk"] for c in calls] == [False, True], (
        "先不带 CDK 查版本，再带 CDK 拿地址"
    )
    assert calls[1]["prefer_full"] is True, "带 CDK 那次必须要全量包"
    assert updater_harness["fingerprint"].calls == 1
    assert any("与更新基线不一致" in line for line in logs)
    assert not any("cdk-secret" in line for line in logs)


@pytest.mark.asyncio
async def test_fingerprint_match_with_cdk_keeps_delta(
    tmp_path: Path, updater_harness: dict[str, Any]
) -> None:
    updater_harness["install"]("v1.1.0", matches=True)

    await update_maafw_project_if_needed(
        tmp_path,
        _interface_model(),
        source_config={"package_source": "mirrorchyan", "mirror_cdk": "cdk-secret"},
    )

    assert updater_harness["mirror"].calls[1]["prefer_full"] is False
    assert updater_harness["fingerprint"].calls == 1


@pytest.mark.asyncio
async def test_up_to_date_project_never_computes_fingerprint(
    tmp_path: Path, updater_harness: dict[str, Any]
) -> None:
    """绝大多数运行前检查的结果是「已是最新」，那 ~2s 一次都不该花。"""

    updater_harness["install"]("v1.0.0", matches=False)

    result = await update_maafw_project_if_needed(
        tmp_path,
        _interface_model(),
        source_config={"package_source": "mirrorchyan", "mirror_cdk": "cdk-secret"},
    )

    assert result.updated is False
    assert updater_harness["fingerprint"].calls == 0


@pytest.mark.asyncio
async def test_github_source_never_computes_fingerprint(
    tmp_path: Path, updater_harness: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub Release 只有全量包，差量包的前提不成立，不算指纹。"""

    updater_harness["install"]("v1.1.0", matches=False)

    async def no_release(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(updater, "_check_github_release_update", no_release)

    await update_maafw_project_if_needed(
        tmp_path, _interface_model(), source_config={"package_source": "github_release"}
    )

    assert updater_harness["fingerprint"].calls == 0
    assert all(c["prefer_full"] is False for c in updater_harness["mirror"].calls)
