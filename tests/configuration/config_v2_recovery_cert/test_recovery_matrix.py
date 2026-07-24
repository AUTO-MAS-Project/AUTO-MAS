"""RECOVERY_MATRIX: 6 个 FAULT_POINTS 崩溃中断后的恢复语义认证。

验证两层：
1. AtomicGenerationStore 层（8 生产根）：每个 fault point 后重新打开 store，
   按 generation_store 契约验证 old/new authority、orphan 可枚举、CAS 不变。
2. AuthoritativeConfigurationRuntime 层：迁移中途 fault 后 owner 必须释放；
   重新 initialize 的行为按 fault point 分类（fail-closed vs auto-recover）。

关键设计：``after_current_replace`` 之前任何 fault 都不创建 CURRENT；
此时若已留下 published/staging 状态，重新 load_current 会抛
``GenerationRecoveryRequiredError``（fail-closed，要求显式恢复决策）。
仅唯一、完整的初代 published generation 可由操作员以 generation + manifest
hash 双重确认后恢复；其余情况仍须人工诊断，绝不自动选择 orphan。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.configuration import config_manager
from app.configuration import production as production_module
from app.configuration.authoritative import (
    AUTHORITATIVE_STORE_DIRECTORY_NAME,
    AuthoritativeConfigurationRuntime,
    AuthoritativeRuntimeOwnershipError,
)
from app.configuration.compat.legacy_original_snapshot import (
    ensure_legacy_original_snapshot,
)
from app.configuration.persistence import (
    AtomicGenerationStore,
    GenerationConflictError,
    NoCommittedGenerationError,
)
from app.configuration.persistence.coordinator import (
    TransactionGenerationCommitError,
)
from app.configuration.persistence.generation_store import (
    FAULT_POINTS,
    GenerationRecoveryRequiredError,
)
from app.configuration.production import PRODUCTION_ROOT_NAMES

from .conftest import safe_close, try_initialize
from .corpus_variants import build_all_variants, write_corpus_to_dir


class _InjectedFault(RuntimeError):
    """标记注入的故障，区别于真实异常。"""


def _eight_root_payloads() -> dict[str, bytes]:
    """构造 8 个生产根的字节载荷（transport-neutral，store 不解析内容）。"""
    return {
        name: f"{name}-payload-v1".encode("utf-8")
        for name in PRODUCTION_ROOT_NAMES
    }


def _updated_payloads() -> dict[str, bytes]:
    return {
        name: f"{name}-payload-v2".encode("utf-8")
        for name in PRODUCTION_ROOT_NAMES
    }


# =====================================================================
# Level A: AtomicGenerationStore 8-root crash recovery
# =====================================================================


@pytest.mark.parametrize("fault_point", list(FAULT_POINTS))
def test_store_crash_recovery_each_fault_point(fault_point, tmp_path):
    """每个 fault point 注入后：CURRENT 状态、orphan 可枚举、CAS 不变。

    契约（来自 generation_store._commit_locked 与 test_generation_store）：
    - after_current_replace：新 generation 已提交，orphan=0
    - 其余 fault point：旧 generation 仍是 CURRENT，orphan≥1 可枚举
    - orphan revision 严格小于下次成功 commit 的 revision
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "store"
        baseline_store = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
        )
        baseline = baseline_store.commit(
            _eight_root_payloads(),
            expected_generation=None,
            expected_revision=0,
        )

        def fault_hook(actual_point: str) -> None:
            if actual_point == fault_point:
                raise _InjectedFault(fault_point)

        faulting_store = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
            fault_hook=fault_hook,
        )
        with pytest.raises(_InjectedFault, match=fault_point):
            faulting_store.commit(
                _updated_payloads(),
                expected_generation=baseline.generation,
                expected_revision=baseline.revision,
            )

        reopened = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
        )
        current = reopened.read_current()

        if fault_point == "after_current_replace":
            # 新 generation 已是 CURRENT
            assert current.roots == _updated_payloads(), (
                f"{fault_point}: 新载荷应已提交"
            )
            assert current.revision == baseline.revision + 1
            assert reopened.list_orphans() == (), (
                f"{fault_point}: 不应留 orphan"
            )
        else:
            # 旧 generation 仍是 CURRENT
            assert current.generation == baseline.generation
            assert current.roots == _eight_root_payloads()
            orphans = reopened.list_orphans()
            assert len(orphans) >= 1, (
                f"{fault_point}: 应留至少 1 个 orphan"
            )
            # orphan 必须 valid（除可能的部分写入）
            kinds = {o.kind for o in orphans}
            expected_kind = (
                "published"
                if fault_point
                in {"after_generation_rename", "before_current_replace"}
                else "staging"
            )
            assert expected_kind in kinds, (
                f"{fault_point}: orphan kinds={kinds} 缺 {expected_kind}"
            )
            # orphan revision 必须 < 下次成功 commit revision
            for orphan in orphans:
                if orphan.revision is not None:
                    assert orphan.revision > baseline.revision, (
                        f"{fault_point}: orphan revision {orphan.revision} "
                        f"应大于 baseline {baseline.revision}"
                    )


def test_store_orphan_never_auto_committed(tmp_path):
    """published orphan 不会被后续 commit 自动覆盖或提升为 CURRENT。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "store"
        store = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
        )
        baseline = store.commit(
            _eight_root_payloads(),
            expected_generation=None,
            expected_revision=0,
        )

        def fault_hook(point: str) -> None:
            if point == "after_generation_rename":
                raise _InjectedFault("after_generation_rename")

        faulting = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
            fault_hook=fault_hook,
        )
        with pytest.raises(_InjectedFault):
            faulting.commit(
                _updated_payloads(),
                expected_generation=baseline.generation,
                expected_revision=baseline.revision,
            )

        orphan = store.list_orphans()[0]
        orphan_root_path = (
            store.generations_directory
            / orphan.generation
            / "roots"
            / "Config.bin"
        )
        orphan_bytes = orphan_root_path.read_bytes()
        assert orphan_bytes == b"Config-payload-v2"

        # 后续 commit 应跳过 orphan revision
        committed = store.commit(
            {name: f"{name}-v3".encode() for name in PRODUCTION_ROOT_NAMES},
            expected_generation=baseline.generation,
            expected_revision=baseline.revision,
        )
        assert committed.revision > orphan.revision
        # orphan 字节未被覆盖
        assert orphan_root_path.read_bytes() == orphan_bytes


def test_store_durable_current_replace_failure_not_treated_as_commit(tmp_path):
    """CURRENT 替换的 durable move 失败 → GenerationDurabilityError，旧 CURRENT 保留。"""
    from app.configuration.persistence import generation_store as gs_module

    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "store"
        store = AtomicGenerationStore(
            store_path,
            required_roots=PRODUCTION_ROOT_NAMES,
        )
        baseline = store.commit(
            _eight_root_payloads(),
            expected_generation=None,
            expected_revision=0,
        )
        real_move = gs_module._durable_move

        def fail_current_replace(source, destination, *, replace_existing):
            if destination == store.current_path:
                from app.configuration.persistence.generation_store import (
                    GenerationDurabilityError,
                )
                raise GenerationDurabilityError("injected")
            real_move(source, destination, replace_existing=replace_existing)

        with patch.object(
            gs_module, "_durable_move", side_effect=fail_current_replace
        ):
            with pytest.raises(Exception):  # GenerationDurabilityError
                store.commit(
                    _updated_payloads(),
                    expected_generation=baseline.generation,
                    expected_revision=baseline.revision,
                )

        # 旧 CURRENT 保留
        assert store.read_current().generation == baseline.generation
        orphans = store.list_orphans()
        kinds = {o.kind for o in orphans}
        assert "published" in kinds
        assert "current-temp" in kinds


# =====================================================================
# Level B: AuthoritativeConfigurationRuntime crash recovery
# =====================================================================


def _patch_store_with_fault(
    fault_point: str,
    seen_points: list[str] | None = None,
):
    """返回 patch 上下文：让 runtime 内部创建的 store 注入 fault_hook。"""
    from app.configuration.authoritative import (
        AtomicGenerationStore as auth_store,
    )
    real_init = auth_store.__init__

    def faulted_init(self, directory, **kwargs):
        def fault_hook(actual_point: str) -> None:
            if seen_points is not None:
                seen_points.append(actual_point)
            if actual_point == fault_point:
                raise _InjectedFault(fault_point)
        kwargs["fault_hook"] = fault_hook
        real_init(self, directory, **kwargs)

    return patch.object(auth_store, "__init__", faulted_init)


@pytest.mark.parametrize("fault_point", list(FAULT_POINTS))
def test_runtime_migration_fault_releases_owner(fault_point, scratch_config):
    """未确认迁移 fault 后释放 owner，已确认 CURRENT fault 则初始化成功。

    协调器故意不传播 fault hook 的原始异常，以免把不可信错误带出持久化层。
    未确认提交统一报 TransactionGenerationCommitError；CURRENT 已替换后的
    fault 通过 durable read-back 确认，因此属于成功提交。
    """
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(variants["normal"]["corpus"], scratch_config)

    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    seen_points: list[str] = []
    with _patch_store_with_fault(fault_point, seen_points):
        state, err = try_initialize(runtime)
    assert seen_points and seen_points[-1] == fault_point

    if fault_point == "after_current_replace":
        try:
            assert err is None, (
                f"{fault_point}: CURRENT 已替换后应被确认: {err!r}"
            )
            assert state is not None
            assert state.initialized_from == "legacy-original"
        finally:
            safe_close(runtime)
        return

    assert state is None
    assert isinstance(err, TransactionGenerationCommitError), (
        f"{fault_point}: 预期 fail-closed TransactionGenerationCommitError，"
        f"实际 {type(err).__name__}: {err}"
    )

    # owner 必须释放：新 runtime 可 acquire（即使 initialize 会再失败）
    runtime2 = AuthoritativeConfigurationRuntime(scratch_config)
    try:
        with _patch_store_with_fault(fault_point):
            state2, err2 = try_initialize(runtime2)
        # 不强制要求第二次成功；但不应是 OwnershipError
        assert not isinstance(err2, AuthoritativeRuntimeOwnershipError), (
            f"{fault_point}: owner 未释放，二次 initialize 被永久阻塞"
        )
    finally:
        safe_close(runtime2)


def test_runtime_migration_fail_closed_when_state_retained(scratch_config):
    """迁移中途 fault（after_generation_rename）后 store 留下 published orphan，
    重新 initialize 应 fail-closed 抛 GenerationRecoveryRequiredError。

    inferred: 这是 Alpha P1 已知缺口——迁移中途崩溃需操作员介入：
    1. list_orphans() 枚举遗留状态
    2. 显式清理 .config-v2-authoritative/<snapshot>/ 或恢复
    3. r6 rollback bundle 此时不存在（迁移未完成）
    """
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(variants["normal"]["corpus"], scratch_config)

    fault_point = "after_generation_rename"
    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    seen_points: list[str] = []
    with _patch_store_with_fault(fault_point, seen_points):
        _, err = try_initialize(runtime)
    assert seen_points and seen_points[-1] == fault_point
    assert isinstance(err, TransactionGenerationCommitError)

    # 重新 initialize 不注入 fault
    runtime2 = AuthoritativeConfigurationRuntime(scratch_config)
    state2, err2 = try_initialize(runtime2)
    try:
        # 已留下 published orphan 但无 CURRENT → GenerationRecoveryRequiredError
        assert isinstance(err2, GenerationRecoveryRequiredError), (
            f"预期 GenerationRecoveryRequiredError，实际 {type(err2).__name__}: {err2}"
        )
    finally:
        safe_close(runtime2)


def test_runtime_migration_resumes_after_explicit_genesis_confirmation(
    scratch_config,
):
    """唯一初代 orphan 必须显式确认后才可恢复为 CURRENT。"""
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(variants["normal"]["corpus"], scratch_config)
    snapshot = ensure_legacy_original_snapshot(scratch_config)
    original_manifest = snapshot.manifest_path.read_bytes()

    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    with _patch_store_with_fault("after_generation_rename"):
        _, err = try_initialize(runtime)
    assert isinstance(err, TransactionGenerationCommitError)

    recovery_store = AtomicGenerationStore(
        runtime.store_directory,
        required_roots=PRODUCTION_ROOT_NAMES,
    )
    orphans = recovery_store.list_orphans()
    assert [(item.kind, item.valid) for item in orphans] == [
        ("published", True)
    ]
    candidate = recovery_store.inspect_generation(orphans[0].generation)
    recovered = recovery_store.recover_initial_generation(
        generation=candidate.generation,
        manifest_sha256=candidate.manifest_sha256,
    )
    assert recovered.generation == candidate.generation
    assert snapshot.manifest_path.read_bytes() == original_manifest

    resumed = AuthoritativeConfigurationRuntime(scratch_config)
    state, resumed_error = try_initialize(resumed)
    try:
        assert resumed_error is None
        assert state is not None
        assert state.initialized_from == "current-generation"
        assert state.generation == candidate.generation
    finally:
        safe_close(resumed)


def test_runtime_migration_before_staging_write_fails_closed(scratch_config):
    """before_staging_write fault 的空 staging 也需要显式恢复决策。"""
    variants = {v["name"]: v for v in build_all_variants()}
    write_corpus_to_dir(variants["normal"]["corpus"], scratch_config)

    fault_point = "before_staging_write"
    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    seen_points: list[str] = []
    with _patch_store_with_fault(fault_point, seen_points):
        _, err = try_initialize(runtime)
    assert seen_points and seen_points[-1] == fault_point
    assert isinstance(err, TransactionGenerationCommitError)

    # 空 staging 仍是 retained state，不能静默开始新的 genesis。
    runtime2 = AuthoritativeConfigurationRuntime(scratch_config)
    state2, err2 = try_initialize(runtime2)
    try:
        assert isinstance(err2, GenerationRecoveryRequiredError), (
            f"before_staging_write 后应 fail-closed，"
            f"实际 {type(err2).__name__}: {err2}"
        )
    finally:
        safe_close(runtime2)


def test_runtime_restart_loads_current_after_successful_migration(
    normal_corpus_config,
):
    """成功迁移后重启：initialized_from=current-generation，generation 不变。"""
    runtime = AuthoritativeConfigurationRuntime(normal_corpus_config)
    state1, err = try_initialize(runtime)
    assert err is None
    first_gen = state1.generation
    runtime.close()

    runtime2 = AuthoritativeConfigurationRuntime(normal_corpus_config)
    state2, err2 = try_initialize(runtime2)
    try:
        assert err2 is None
        assert state2.initialized_from == "current-generation"
        assert state2.generation == first_gen
    finally:
        safe_close(runtime2)


def test_legacy_original_snapshot_immutable_after_migration(normal_corpus_config):
    """迁移后 legacy original snapshot 字节不变（manifest sha256 自洽）。"""
    import hashlib

    snapshot = ensure_legacy_original_snapshot(normal_corpus_config)
    manifest_path = snapshot.manifest_path
    original_manifest_hash = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()

    runtime = AuthoritativeConfigurationRuntime(normal_corpus_config)
    state, err = try_initialize(runtime)
    assert err is None
    runtime.close()

    # 迁移后 manifest 字节不变
    assert (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == original_manifest_hash
    ), "legacy original snapshot manifest 在迁移后被修改"


def test_runtime_prepare_commit_fault_preserves_current(normal_corpus_config):
    """prepare_commit（后续事务提交）中途 fault → 旧 CURRENT 保留。

    inferred: AuthoritativeConfigurationRuntime._prepare_commit 调用
    coordinator.commit_transaction，最终走 store.commit。注入
    before_current_replace fault → 旧 generation 仍是 CURRENT，
    runtime._state 不被推进（_prepare_commit 抛异常，_current 不更新）。
    """
    runtime = AuthoritativeConfigurationRuntime(normal_corpus_config)
    state, err = try_initialize(runtime)
    assert err is None
    current_gen_before = state.generation

    captured = {}
    previous_value = runtime.roots.config.Function.IfSilence

    async def _do_prepare_commit_with_fault():
        # 通过真实 transaction 入口触发 prepare hook，不直接调用私有方法。
        store = runtime._store
        original_fault = store._fault

        def faulting_fault(point):
            captured["point"] = point
            if point == "before_current_replace":
                raise _InjectedFault("before_current_replace")
            original_fault(point)

        store._fault = faulting_fault
        try:
            async with config_manager.transaction():
                runtime.roots.config.Function.IfSilence = not previous_value
                await runtime.roots.config.commit()
        finally:
            store._fault = original_fault

    try:
        with pytest.raises(TransactionGenerationCommitError):
            asyncio.run(_do_prepare_commit_with_fault())
        assert captured["point"] == "before_current_replace"
        # 旧 CURRENT 保留
        assert runtime.state.generation == current_gen_before, (
            "prepare_commit fault 后 current generation 被推进"
        )
        assert runtime._store.read_current().generation == current_gen_before
        assert runtime.roots.config.Function.IfSilence == previous_value, (
            "prepare_commit fault 后 live config 未回滚"
        )
    finally:
        safe_close(runtime)
