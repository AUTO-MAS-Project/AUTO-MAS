"""MIGRATION_CORPUS_MATRIX: 9 类输入语料驱动 Config v2 authoritative 升级/重启/回滚。

对每个变体验证：
1. 升级（legacy JSON → authoritative generation）是否成功
2. 持久化（CURRENT 文件存在、generation 目录布局合法）
3. 重启读取（关闭 runtime 后重新 initialize，initialized_from=current-generation）
4. 失败回滚（损坏语料不留下部分 ACTIVE 根，runtime 可再次 initialize）
5. 原文件保留（legacy JSON 与不可变 original snapshot 共存）
6. r6 rollback bundle（密文 only，不泄明文）

所有测试在 tempfile.TemporaryDirectory 中运行；绝不读取真实 config/。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

import pytest

from app.configuration.authoritative import (
    AUTHORITATIVE_STORE_DIRECTORY_NAME,
    AuthoritativeConfigurationRuntime,
    LegacySnapshotDecodeError,
    ROLLBACK_EXPORT_DIRECTORY_NAME,
)
from app.configuration.compat.legacy_original_snapshot import (
    ensure_legacy_original_snapshot,
)
from app.configuration.persistence import NoCommittedGenerationError

from .corpus_variants import (
    VARIANT_NAMES,
    build_all_variants,
    write_corpus_to_dir,
)


# Collection must not instantiate synthetic ciphertext before the package
# deterministic-DPAPI fixture is active.
VARIANT_IDS = VARIANT_NAMES


def _try_initialize(runtime: AuthoritativeConfigurationRuntime):
    """初始化 runtime，返回 (state, error)；失败时清理 owner。"""
    import asyncio

    async def _do():
        return await runtime.initialize()

    try:
        state = asyncio.run(_do())
        return state, None
    except BaseException as exc:
        # 失败时 runtime 内部已尝试清理；若 owner 仍残留则显式 close
        try:
            runtime.close()
        except Exception:
            pass
        return None, exc


def _safe_close(runtime: AuthoritativeConfigurationRuntime | None) -> None:
    if runtime is None:
        return
    try:
        runtime.close()
    except Exception:
        pass


def _read_current_generation_name(store_dir: Path) -> str | None:
    current_path = store_dir / "CURRENT"
    if not current_path.exists():
        return None
    payload = json.loads(current_path.read_text(encoding="utf-8"))
    return payload.get("generation")


@pytest.mark.parametrize("variant_name", VARIANT_IDS)
def test_migration_corpus_matrix(variant_name, scratch_config):
    """每个变体驱动完整升级 → 持久化 → 重启 → 失败回滚 → rollback bundle。

    根据变体 expect_upgrade 预期：
    - True：升级成功，重启加载 current-generation，rollback bundle 无明文
    - False：升级抛预期异常，runtime 可再次 initialize（owner 释放）
    - "unknown"：记录实际结果，不强制断言
    """
    variants = {v["name"]: v for v in build_all_variants()}
    variant = variants[variant_name]
    write_corpus_to_dir(variant["corpus"], scratch_config)

    # ── 步骤 1: ensure_legacy_original_snapshot 应总是成功（捕获阶段只读字节）
    snapshot = ensure_legacy_original_snapshot(scratch_config)
    assert snapshot.generation.startswith("original-"), (
        f"{variant_name}: original snapshot generation 命名异常: {snapshot.generation}"
    )
    # original snapshot 落到 config_dir/.config-v2-original/
    original_dir = scratch_config / ".config-v2-original"
    assert original_dir.exists(), f"{variant_name}: .config-v2-original 不存在"

    # ── 步骤 2: initialize（升级）
    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    state, err = _try_initialize(runtime)
    expect_upgrade = variant["expect_upgrade"]

    if expect_upgrade is True:
        assert state is not None, (
            f"{variant_name}: 预期升级成功但抛 {err!r}"
        )
        assert state.initialized_from == "legacy-original", (
            f"{variant_name}: 首次 initialized_from 应为 legacy-original，"
            f"实际 {state.initialized_from}"
        )
        _assert_persistence_layout(variant_name, scratch_config, state)
        _assert_legacy_original_preserved(variant_name, scratch_config, variant)
        _test_rollback_bundle(variant_name, scratch_config, runtime, variant)
        _test_restart_loads_current(variant_name, scratch_config, runtime)
        _safe_close(runtime)
    elif expect_upgrade is False:
        assert err is not None, (
            f"{variant_name}: 预期升级失败但实际成功"
        )
        expected_error = variant.get("expect_upgrade_error", "")
        actual_type = type(err).__name__
        assert actual_type == expected_error, (
            f"{variant_name}: 预期异常 {expected_error}，实际 {actual_type}: {err}"
        )
        # 失败后 owner 必须释放，使后续 initialize 可重试
        _test_runtime_releasable_after_failure(variant_name, scratch_config)
        # 不应留下部分 ACTIVE 根或残留 CURRENT
        _assert_no_partial_current(variant_name, scratch_config)
    else:  # "unknown"
        # 记录实际结果但不强制断言；用于 KNOWN_GAPS
        if state is not None:
            _assert_persistence_layout(variant_name, scratch_config, state)
            _test_rollback_bundle(variant_name, scratch_config, runtime, variant)
            _safe_close(runtime)
        else:
            _test_runtime_releasable_after_failure(variant_name, scratch_config)


def _assert_persistence_layout(
    variant_name: str,
    config_dir: Path,
    state,
) -> None:
    """验证持久化布局：.config-v2-authoritative/g-.../{CURRENT,generations,staging,LOCK}。"""
    store_dir = (
        config_dir / AUTHORITATIVE_STORE_DIRECTORY_NAME / state.source_snapshot_generation
    )
    assert store_dir.exists(), f"{variant_name}: authoritative store 目录不存在"
    assert (store_dir / "CURRENT").exists(), f"{variant_name}: CURRENT 文件不存在"
    assert (store_dir / "LOCK").exists(), f"{variant_name}: LOCK 文件不存在"
    assert (store_dir / "generations").is_dir(), f"{variant_name}: generations/ 不存在"
    assert (store_dir / "staging").is_dir(), f"{variant_name}: staging/ 不存在"

    gen_name = _read_current_generation_name(store_dir)
    assert gen_name is not None, f"{variant_name}: CURRENT 缺 generation 字段"
    assert re.match(r"g-\d{20}-[0-9a-f]{32}", gen_name), (
        f"{variant_name}: generation 命名不合规: {gen_name}"
    )
    gen_dir = store_dir / "generations" / gen_name
    assert gen_dir.is_dir(), f"{variant_name}: generation 目录不存在: {gen_name}"
    assert (gen_dir / "manifest.json").is_file(), (
        f"{variant_name}: manifest.json 不存在"
    )
    assert (gen_dir / "roots").is_dir(), f"{variant_name}: roots/ 不存在"


def _assert_legacy_original_preserved(
    variant_name: str,
    config_dir: Path,
    variant: dict,
) -> None:
    """验证 legacy JSON 原文件仍存在（升级不删除/覆盖原文件）。"""
    for file_name in variant["corpus"]:
        # garbled_json / partial_write 的 corpus value 是 bytes；文件仍应存在
        assert (config_dir / file_name).exists(), (
            f"{variant_name}: 原文件 {file_name} 被升级删除"
        )


def _test_restart_loads_current(
    variant_name: str,
    config_dir: Path,
    runtime: AuthoritativeConfigurationRuntime,
) -> None:
    """关闭 runtime 后重新 initialize，应从 CURRENT 加载而非重新迁移。"""
    # 先记录首次 generation
    first_state = runtime.state
    # close 释放 owner
    runtime.close()

    # 重新 initialize
    runtime2 = AuthoritativeConfigurationRuntime(config_dir)
    state2, err = _try_initialize(runtime2)
    assert state2 is not None, (
        f"{variant_name}: 重启 initialize 失败: {err!r}"
    )
    assert state2.initialized_from == "current-generation", (
        f"{variant_name}: 重启应加载 current-generation，"
        f"实际 {state2.initialized_from}"
    )
    assert state2.generation == first_state.generation, (
        f"{variant_name}: 重启后 generation 不一致"
    )
    _safe_close(runtime2)


def _test_rollback_bundle(
    variant_name: str,
    config_dir: Path,
    runtime: AuthoritativeConfigurationRuntime,
    variant: dict,
) -> None:
    """导出 r6 rollback bundle，验证布局与密文 only。"""
    bundle_path = runtime.export_r6_rollback_bundle()
    assert bundle_path.exists(), f"{variant_name}: rollback bundle 不存在"
    assert bundle_path.is_dir(), f"{variant_name}: rollback bundle 不是目录"
    manifest = json.loads((bundle_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "auto-mas-r6-config-rollback"
    assert manifest["schema_version"] == 1
    assert len(manifest["roots"]) == 8, (
        f"{variant_name}: rollback bundle 应含 8 个根，实际 {len(manifest['roots'])}"
    )

    # 扫描所有根文件字节，确认不含明文密钥
    plaintext_markers = (
        b"REDACTED",  # 仅占位符本身；明文应是密文格式
        b"password", b"Password",
        b"token", b"Token",  # 字段名允许出现，但值不应是裸明文
    )
    # 实际密文应均为 DPAPI:v1: 前缀或空串
    for record in manifest["roots"]:
        root_file = bundle_path / record["name"]
        content = root_file.read_bytes()
        # 校验 sha256
        import hashlib
        assert hashlib.sha256(content).hexdigest() == record["sha256"], (
            f"{variant_name}: rollback bundle 根 {record['name']} sha256 不匹配"
        )
        # 反序列化检查所有 token-like 字段值为 DPAPI: 前缀或空
        payload = json.loads(content.decode("utf-8"))
        _assert_no_plaintext_secrets(variant_name, record["name"], payload)


def _assert_no_plaintext_secrets(
    variant_name: str,
    file_name: str,
    payload: object,
    path: str = "",
) -> None:
    """递归扫描 payload，所有疑似密钥字段值应为 DPAPI: 前缀或空。

    报告严禁写真实密文——本断言只检测值是否为已知密文格式。
    """
    secret_field_names = {
        "koishitoken", "authorizationcode", "serverchankey",
        "mirrorchyancdk", "githubtoken",
        "sklandtoken", "miyoushetoken", "kurotoken",
        "password", "configraw", "headers",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            sub_path = f"{path}.{key}" if path else key
            if key.lower() in secret_field_names:
                if isinstance(value, str):
                    if value == "":
                        continue
                    assert value.startswith(("DPAPI:v1:", "DPAPI:")), (
                        f"{variant_name}/{file_name}: {sub_path} 值不是密文格式"
                    )
            else:
                _assert_no_plaintext_secrets(variant_name, file_name, value, sub_path)
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_no_plaintext_secrets(
                variant_name, file_name, item, f"{path}[{i}]"
            )


def _test_runtime_releasable_after_failure(
    variant_name: str,
    config_dir: Path,
) -> None:
    """失败后 owner 必须释放，使新的 runtime 可再次 initialize（即使会再次失败）。"""
    runtime2 = AuthoritativeConfigurationRuntime(config_dir)
    _, err2 = _try_initialize(runtime2)
    # 不强制要求第二次成功；但若再次失败也不应抛 AuthoritativeRuntimeOwnershipError
    from app.configuration.authoritative import AuthoritativeRuntimeOwnershipError
    if isinstance(err2, AuthoritativeRuntimeOwnershipError):
        pytest.fail(
            f"{variant_name}: 升级失败后 owner 未释放，导致后续 initialize 被永久阻塞"
        )
    _safe_close(runtime2)


def _assert_no_partial_current(variant_name: str, config_dir: Path) -> None:
    """损坏语料不应留下残留 CURRENT 或部分 ACTIVE 根。

    legacy original snapshot 允许存在（捕获成功），但 authoritative store
    不应有 CURRENT（升级失败不应提交）。
    """
    store_root = config_dir / AUTHORITATIVE_STORE_DIRECTORY_NAME
    if not store_root.exists():
        return
    # 升级失败可能创建 store 目录，但不应有 CURRENT
    for snapshot_dir in store_root.iterdir():
        current = snapshot_dir / "CURRENT"
        assert not current.exists(), (
            f"{variant_name}: 升级失败但留下 CURRENT: {current}"
        )


def test_normal_corpus_roundtrip_uuids_preserved(scratch_config):
    """normal 语料升级 → rollback bundle 后，UUID 应保持与原 legacy 一致。"""
    variants = {v["name"]: v for v in build_all_variants()}
    variant = variants["normal"]
    write_corpus_to_dir(variant["corpus"], scratch_config)

    runtime = AuthoritativeConfigurationRuntime(scratch_config)
    state, err = _try_initialize(runtime)
    assert err is None, f"normal 升级失败: {err!r}"
    assert state is not None

    bundle_path = runtime.export_r6_rollback_bundle()
    # 从 bundle 读取 EmulatorConfig 的 instances
    emu_payload = json.loads(
        (bundle_path / "EmulatorConfig.json").read_bytes().decode("utf-8")
    )
    instance_uids = {item["uid"] for item in emu_payload["instances"]}
    expected = {
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    }
    assert instance_uids == expected, (
        f"UUID 未保持: expected={expected}, actual={instance_uids}"
    )
    # 校验所有 uid 都是合法 UUID 字符串
    for uid_str in instance_uids:
        UUID(uid_str)  # 抛 ValueError 即失败
    _safe_close(runtime)
