"""运行环境预检备忘：读写、目标版本过期判定、失败文本分类。

备忘是更新提交前真建运行环境失败后留下的记录，与更新清单同目录。``kind``
决定下次运行前要不要轻探：只有「索引里没有这个版本」才算 ``binding_unavailable``，
连不上索引、离线、磁盘满都是 ``other``。夹具文本照 uv 0.11.26 / pip 的真实
stderr 抄，别臆造。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.task.MaaFW.tools.core.automas_maafw_project_update.apply import (
    project_state_dir_for,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.precheck_memo import (
    KIND_BINDING_UNAVAILABLE,
    KIND_OTHER,
    PRECHECK_MEMO_NAME,
    REASON_MAX_CHARS,
    classify_precheck_failure,
    classify_precheck_kind,
    clear_runtime_precheck,
    memo_matches_version,
    precheck_memo_path,
    read_runtime_precheck,
    write_runtime_precheck,
)

UV_NO_VERSION = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because there is no version of maafw==5.14.0b1 and you require "
    "maafw==5.14.0b1, we can conclude that your requirements are unsatisfiable."
)
UV_NOT_IN_REGISTRY = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because maafw was not found in the package registry and you require "
    "maafw==5.14.0b1, we can conclude that your requirements are unsatisfiable."
)
PIP_NO_DISTRIBUTION = (
    "ERROR: Could not find a version that satisfies the requirement maafw==5.14.0b1 "
    "(from versions: 5.12.3, 5.13.0, 5.13.1)\n"
    "ERROR: No matching distribution found for maafw==5.14.0b1"
)
DISK_FULL = "[WinError 112] 磁盘空间不足。: 'D:\\\\pool\\\\.staging\\\\maafw-runtime-x'"
UV_OFFLINE = (
    "  × No solution found when resolving dependencies:\n"
    "  ╰─▶ Because maafw was not found in the cache and you require maafw==5.14.0b1, "
    "we can conclude that your requirements are unsatisfiable.\n"
    "      hint: Packages were unavailable because the network was disabled."
)
UV_NETWORK = "error: Request failed after 3 retries\n  Caused by: Failed to fetch: `https://pypi.org/simple/maafw/`"


def _operations(tmp_path: Path) -> Path:
    return tmp_path / "data" / "maafw_update_operations"


def _memo(target: str = "v2.29.0", **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "targetVersion": target,
        "requirement": "maafw==5.14.0b1",
        "kind": KIND_BINDING_UNAVAILABLE,
        "reason": UV_NO_VERSION,
    }
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------


def test_memo_lives_next_to_update_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)

    path = precheck_memo_path(project, operation_root=operations)

    assert path.parent == project_state_dir_for(project, operation_root=operations)
    assert path.name == PRECHECK_MEMO_NAME
    assert path.parent.parent == tmp_path / "data" / "maafw_project_state"


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)

    assert read_runtime_precheck(project, operation_root=operations) is None
    written = write_runtime_precheck(project, _memo(), operation_root=operations)
    memo = read_runtime_precheck(project, operation_root=operations)

    assert written.is_file()
    assert memo is not None
    assert memo["targetVersion"] == "v2.29.0"
    assert memo["requirement"] == "maafw==5.14.0b1"
    assert memo["kind"] == KIND_BINDING_UNAVAILABLE
    assert memo["reason"] == UV_NO_VERSION
    assert memo["attempts"] == 1, "预检那一次就是第一次尝试"
    assert memo["failedAt"], "写入时补上时间戳"
    assert not list(written.parent.glob(".*.tmp")), "原子写不留临时文件"


def test_write_only_keeps_memo_keys_and_truncates_reason(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)

    write_runtime_precheck(
        project,
        _memo(reason="x" * (REASON_MAX_CHARS + 50), previousVersion="v2.28.0"),
        operation_root=operations,
    )
    raw = json.loads(
        precheck_memo_path(project, operation_root=operations).read_text("utf-8")
    )

    assert "previousVersion" not in raw, "闭包里的上下文字段不落盘"
    assert len(raw["reason"]) == REASON_MAX_CHARS


def test_write_normalizes_kind_and_attempts(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)

    write_runtime_precheck(
        project,
        _memo(kind="garbage", attempts="not-a-number", requirement=None),
        operation_root=operations,
    )
    memo = read_runtime_precheck(project, operation_root=operations)

    assert memo is not None
    assert memo["kind"] == KIND_OTHER, "认不出的 kind 一律按 other（不轻探）"
    assert memo["attempts"] == 1
    assert memo["requirement"] == "maafw", "requirement 缺失时记裸的 maafw（D4）"


def test_attempts_written_back(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)
    write_runtime_precheck(project, _memo(), operation_root=operations)

    memo = read_runtime_precheck(project, operation_root=operations)
    assert memo is not None
    memo["attempts"] = int(memo["attempts"]) + 1
    write_runtime_precheck(project, memo, operation_root=operations)

    reread = read_runtime_precheck(project, operation_root=operations)
    assert reread is not None
    assert reread["attempts"] == 2


def test_clear_reports_whether_anything_was_removed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)

    assert clear_runtime_precheck(project, operation_root=operations) is False
    write_runtime_precheck(project, _memo(), operation_root=operations)
    assert clear_runtime_precheck(project, operation_root=operations) is True
    assert read_runtime_precheck(project, operation_root=operations) is None


def test_unreadable_memo_counts_as_absent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    operations = _operations(tmp_path)
    path = precheck_memo_path(project, operation_root=operations)
    path.parent.mkdir(parents=True)

    path.write_text("{not json", encoding="utf-8")
    assert read_runtime_precheck(project, operation_root=operations) is None

    path.write_text(json.dumps({"kind": KIND_OTHER}), encoding="utf-8")
    assert read_runtime_precheck(project, operation_root=operations) is None, (
        "没有目标版本的备忘无从比对，当没有"
    )


# ---------------------------------------------------------------------------
# 过期：目标版本一变备忘就作废
# ---------------------------------------------------------------------------


def test_memo_matches_version_ignores_leading_v_and_case() -> None:
    assert memo_matches_version(_memo("v2.29.0"), "v2.29.0")
    assert memo_matches_version(_memo("v2.29.0"), "2.29.0")
    assert memo_matches_version(_memo("2.29.0"), "V2.29.0")
    assert not memo_matches_version(_memo("v2.29.0"), "v2.29.1")
    assert not memo_matches_version(_memo("v2.29.0"), "")
    assert not memo_matches_version({}, "v2.29.0")


# ---------------------------------------------------------------------------
# kind 分类
# ---------------------------------------------------------------------------


def test_uv_no_version_is_binding_unavailable() -> None:
    assert classify_precheck_kind(UV_NO_VERSION) == KIND_BINDING_UNAVAILABLE


def test_uv_not_in_registry_is_binding_unavailable() -> None:
    assert classify_precheck_kind(UV_NOT_IN_REGISTRY) == KIND_BINDING_UNAVAILABLE


def test_pip_no_matching_distribution_is_binding_unavailable() -> None:
    assert classify_precheck_kind(PIP_NO_DISTRIBUTION) == KIND_BINDING_UNAVAILABLE


def test_disk_full_is_other() -> None:
    assert classify_precheck_kind(DISK_FULL) == KIND_OTHER


def test_offline_and_network_failures_are_not_binding_unavailable() -> None:
    """离线的「not found in the cache」与连不上索引都不是「版本不存在」。"""

    assert classify_precheck_kind(UV_OFFLINE) == KIND_OTHER
    assert classify_precheck_kind(UV_NETWORK) == KIND_OTHER


def test_classify_failure_reads_target_version_from_interface(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.29.0"}), encoding="utf-8"
    )

    info = classify_precheck_failure(
        project, RuntimeError(UV_NO_VERSION), requirement="maafw==5.14.0b1"
    )

    assert info["targetVersion"] == "v2.29.0"
    assert info["requirement"] == "maafw==5.14.0b1"
    assert info["kind"] == KIND_BINDING_UNAVAILABLE
    assert info["reason"] == UV_NO_VERSION.strip()
    assert info["failedAt"]


def test_classify_failure_without_interface_or_requirement(tmp_path: Path) -> None:
    info = classify_precheck_failure(tmp_path / "missing", OSError(DISK_FULL))

    assert info["targetVersion"] == ""
    assert info["requirement"] == "maafw"
    assert info["kind"] == KIND_OTHER
    assert info["reason"] == DISK_FULL


def test_classify_failure_uses_exception_type_when_message_empty(
    tmp_path: Path,
) -> None:
    info = classify_precheck_failure(tmp_path, RuntimeError())

    assert info["reason"] == "RuntimeError"
    assert info["kind"] == KIND_OTHER
