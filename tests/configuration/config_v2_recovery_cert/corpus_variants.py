"""9 类输入语料工厂：r6/legacy JSON → Config v2 shadow/canary/authoritative。

每个变体在 ``build_desensitized_legacy_corpus``（来自 ``config_v2_cert.corpus``）
的基准之上叠加一类真实可能出现的异常输入，用于驱动 NativeConfigFacade /
AuthoritativeConfigurationRuntime 的升级、持久化、重启读取、失败回滚与原文件
保留边界。

设计原则：
- 绝不包含真实明文密钥；密文字段统一使用占位 ``DPAPI:v1:REDACTED_*``。
- 每个变体提供 ``name``（机器可读 ID）、``description``（人类可读）、
  ``expect_upgrade``（预期是否应成功升级）、``expect_load_current``（重启
  后是否能加载 CURRENT）、``corpus``（8 个根文件名到 dict 或 bytes 的映射）。
- ``corpus`` 的 value 可以是 ``dict``（合法 JSON 对象）或 ``bytes``（已序列化
  字节，用于乱码 / 部分写入 / 二进制损坏测试）。
"""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from tests.configuration.config_v2_cert.corpus import (
    build_desensitized_legacy_corpus,
)
from app.utils.security import encrypt_config_value

# 审计语料中的显式脱敏标记。它故意不是可解密 DPAPI blob，不能直接喂给
# authoritative runtime；见 ``variant_redacted_ciphertext`` 的 fail-closed
# 负例。成功路径只在本模块深拷贝出的临时测试语料中 materialize。
_SECRET_PLACEHOLDER = "DPAPI:v1:REDACTED_BASE64_PLACEHOLDER"

_SAFE_PLAINTEXT_BY_FIELD = {
    "MirrorChyanCDK": "fixture-cdk",
    "GitHubToken": "fixture-github",
    "Url": "https://example.invalid/automas-recovery-cert",
    "Headers": "{}",
    "ConfigRaw": "{}",
    "MiyousheToken": "fixture-miyoushe",
    "KuroToken": "fixture-kuro",
    "SklandToken": "fixture-skland",
}


def _raw_base_corpus() -> dict[str, dict[str, object]]:
    """Return the untouched desensitized corpus for explicit negative cases."""

    return copy.deepcopy(build_desensitized_legacy_corpus())


def _materialize_test_ciphertexts(value: object, path: tuple[str, ...] = ()) -> object:
    """Replace only known audit markers in an in-memory test copy.

    Production still rejects malformed ``DPAPI:`` input.  This helper creates
    non-sensitive, schema-valid ciphertext through the same encryption entry
    point used by Config v2, after the package-local deterministic DPAPI
    fixture is active.  Unknown paths are rejected rather than guessed.
    """

    if isinstance(value, dict):
        return {
            key: _materialize_test_ciphertexts(item, path + (str(key),))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _materialize_test_ciphertexts(item, path + (str(index),))
            for index, item in enumerate(value)
        ]
    if value != _SECRET_PLACEHOLDER:
        return value

    field_name = path[-1] if path else ""
    try:
        plaintext = _SAFE_PLAINTEXT_BY_FIELD[field_name]
    except KeyError as exc:
        raise AssertionError(
            "recovery corpus contains an unclassified redacted secret at "
            + ".".join(path)
        ) from exc
    return encrypt_config_value(plaintext)


def _base_corpus() -> dict[str, dict[str, object]]:
    """Return an isolated, decryptable synthetic corpus for success paths."""

    raw = _raw_base_corpus()
    return _materialize_test_ciphertexts(raw)  # type: ignore[return-value]


# ---------------------------------------------------------------------
# 变体 1: normal —— 完整脱敏语料，所有根齐全，预期成功升级
# ---------------------------------------------------------------------

def variant_normal() -> dict[str, Any]:
    return {
        "name": "normal",
        "description": "完整脱敏 8 根语料，所有字段齐全且为规范形式",
        "expect_upgrade": True,
        "expect_load_current": True,
        "expect_roundtrip_equivalent": True,
        "corpus": _base_corpus(),
    }


# ---------------------------------------------------------------------
# 变体 2: missing_fields —— 缺字段（模拟 r6 部分字段缺失，依赖默认值）
# ---------------------------------------------------------------------

def variant_missing_fields() -> dict[str, Any]:
    corpus = _base_corpus()
    # Config.Update.MirrorChyanCDK / GitHubToken 缺失
    update = corpus["Config.json"]["Update"]  # type: ignore[index]
    del update["MirrorChyanCDK"]  # type: ignore[arg-type]
    del update["GitHubToken"]  # type: ignore[arg-type]
    # Config.Notify.SMTPServerAddress 缺失
    notify = corpus["Config.json"]["Notify"]  # type: ignore[index]
    del notify["SMTPServerAddress"]  # type: ignore[arg-type]
    # ScriptConfig 第一个脚本的 Script.ScriptPath 缺失
    script1 = corpus["ScriptConfig.json"]["00000000-0000-0000-0000-000000000001"]  # type: ignore[index]
    del script1["Script"]["ScriptPath"]  # type: ignore[index]
    return {
        "name": "missing_fields",
        "description": "Config.Update / Config.Notify / ScriptConfig 缺少部分字段，依赖 v2 默认值填充",
        "expect_upgrade": True,
        "expect_load_current": True,
        "expect_roundtrip_equivalent": False,  # 默认值会显式回填
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 3: legacy_aliases —— 旧字段名（r6 历史别名）
# ---------------------------------------------------------------------

def variant_legacy_aliases() -> dict[str, Any]:
    """注入 r6 历史别名：Data.Stage / Emulator.Data.Type / PluginConfig.Data.Config。

    这些别名在 ``legacy_*_to_wire`` 转换器中应当被识别或丢弃；若转换器严格
    拒绝未知字段则 expect_upgrade=False。
    """
    corpus = _base_corpus()
    config = corpus["Config.json"]  # type: ignore[index]
    # Data.Stage 是 r6 早期历史别名（已被 StageData 替代）
    config["Data"]["Stage"] = "0-1"  # type: ignore[index]
    # Emulator.Data.Type 是历史别名（已被 Info.Type 替代）
    emu1 = corpus["EmulatorConfig.json"]["00000000-0000-0000-0000-000000000001"]  # type: ignore[index]
    emu1["Data"] = {"Type": "ldplayer"}  # type: ignore[index]
    # PluginConfig.Data.Config 是历史别名
    plugin = corpus["PluginConfig.json"]  # type: ignore[index]
    plugin["Data"]["Config"] = "{}"  # type: ignore[index]
    return {
        "name": "legacy_aliases",
        "description": "r6 历史别名（Data.Stage / Emulator.Data.Type / PluginConfig.Data.Config）",
        "expect_upgrade": "unknown",  # 取决于转换器是否严格拒绝未知字段
        "expect_load_current": "unknown",
        "expect_roundtrip_equivalent": False,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 4: garbled_json —— 乱码 JSON 字节（损坏）
# ---------------------------------------------------------------------

def variant_garbled_json() -> dict[str, Any]:
    """Config.json 字节为损坏 JSON。

    ensure_legacy_original_snapshot 捕获阶段只读字节，所以快照会成功创建；
    load_legacy_original_roots 解析阶段应抛 LegacySnapshotDecodeError。
    """
    corpus = _base_corpus()
    corpus["Config.json"] = b'{"broken": \x00\xff garbage'  # type: ignore[assignment]
    return {
        "name": "garbled_json",
        "description": "Config.json 字节为损坏 JSON（含 NUL / 0xFF / 未闭合）",
        "expect_upgrade": False,
        "expect_load_current": False,
        "expect_upgrade_error": "LegacySnapshotDecodeError",
        "expect_roundtrip_equivalent": False,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 5: encrypted_fields —— 密文字段（合法 DPAPI 占位）
# ---------------------------------------------------------------------

def variant_encrypted_fields() -> dict[str, Any]:
    """所有敏感字段显式为可解密的 synthetic DPAPI 密文。

    验证：升级不试图再次加密已密文值；落盘仍为密文；API 明文投影可解。
    """
    corpus = _base_corpus()
    # 额外把 GameSign 的 KuroToken 也设为密文（基准为空）
    for uid, account in corpus["GameSignAccounts.json"].items():  # type: ignore[union-attr]
        if uid == "instances":
            continue
        account["GameSignAccount"]["KuroToken"] = encrypt_config_value(  # type: ignore[index]
            _SAFE_PLAINTEXT_BY_FIELD["KuroToken"]
        )
    return {
        "name": "encrypted_fields",
        "description": "所有敏感字段（token/cookie/key/code）为可解密测试密文",
        "expect_upgrade": True,
        "expect_load_current": True,
        "expect_roundtrip_equivalent": True,
        "expect_no_plaintext_on_disk": True,
        "corpus": corpus,
    }


def variant_redacted_ciphertext() -> dict[str, Any]:
    """Raw audit markers must never be accepted as real user ciphertext."""

    return {
        "name": "redacted_ciphertext",
        "description": "脱敏 DPAPI 占位符不得绕过真实解密与字段校验",
        "expect_upgrade": False,
        "expect_load_current": False,
        "expect_upgrade_error": "ConfigAggregateError",
        "expect_roundtrip_equivalent": False,
        "corpus": _raw_base_corpus(),
    }


# ---------------------------------------------------------------------
# 变体 6: partial_write —— 部分写入（模拟崩溃中断的 JSON）
# ---------------------------------------------------------------------

def variant_partial_write() -> dict[str, Any]:
    """ScriptConfig.json 为部分写入的截断 JSON（前缀合法，后缀缺失）。

    模拟 r6 在写盘过程中崩溃的中间状态。
    """
    corpus = _base_corpus()
    full = json.dumps(
        corpus["ScriptConfig.json"],  # type: ignore[arg-type]
        ensure_ascii=False,
        indent=4,
    )
    # 截取前 60% 作为部分写入
    truncated = full[: len(full) * 6 // 10].encode("utf-8")
    corpus["ScriptConfig.json"] = truncated  # type: ignore[assignment]
    return {
        "name": "partial_write",
        "description": "ScriptConfig.json 为崩溃中断的部分写入（截断 JSON）",
        "expect_upgrade": False,
        "expect_load_current": False,
        "expect_upgrade_error": "LegacySnapshotDecodeError",
        "expect_roundtrip_equivalent": False,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 7: conflicting_uids —— 冲突 UID（同一 UID 出现在多个根或同根重复）
# ---------------------------------------------------------------------

def variant_conflicting_uids() -> dict[str, Any]:
    """两个 Emulator 实例使用相同 UID（00000000-0000-0000-0000-000000000001）。

    验证：转换器或 v2 collection 是否检测到冲突，或在激活阶段失败。
    """
    corpus = _base_corpus()
    emu = corpus["EmulatorConfig.json"]  # type: ignore[index]
    # 把第二个 emulator 的 UID 改为与第一个相同
    instances = emu["instances"]  # type: ignore[index]
    instances[1]["uid"] = "00000000-0000-0000-0000-000000000001"  # type: ignore[index]
    # 删除第二个独立条目，把数据合并到第一个
    del emu["00000000-0000-0000-0000-000000000002"]  # type: ignore[index]
    return {
        "name": "conflicting_uids",
        "description": "EmulatorConfig 两个实例声明相同 UID（instances 列表冲突）",
        "expect_upgrade": "unknown",  # 取决于转换器是否在 instances 列表层去重
        "expect_load_current": "unknown",
        "expect_roundtrip_equivalent": False,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 8: cross_root_reference —— 跨根引用（QueueItem.ScriptId 指向不存在脚本）
# ---------------------------------------------------------------------

def variant_cross_root_reference() -> dict[str, Any]:
    """QueueItem.Info.ScriptId 引用一个不存在于 ScriptConfig 的 UID。

    验证：转换器是否接受悬空引用；激活后 NativeConfigFacade.del_script
    级联删除是否安全（无匹配则跳过）。
    """
    corpus = _base_corpus()
    queue1 = corpus["QueueConfig.json"]["00000000-0000-0000-0000-000000000001"]  # type: ignore[index]
    queue_items = queue1["SubConfigsInfo"]["QueueItem"]  # type: ignore[index]
    # 把第一个 QueueItem 的 ScriptId 指向不存在的 UID
    first_item_uid = queue_items["instances"][0]["uid"]  # type: ignore[index]
    queue_items[first_item_uid]["Info"]["ScriptId"] = (  # type: ignore[index]
        "ffffffff-ffff-ffff-ffff-ffffffffffff"
    )
    return {
        "name": "cross_root_reference",
        "description": "QueueItem.ScriptId 指向不存在于 ScriptConfig 的 UID（悬空引用）",
        "expect_upgrade": True,  # ScriptId 是 str 字段，不做引用完整性校验
        "expect_load_current": True,
        "expect_roundtrip_equivalent": True,
        "expect_cascade_delete_safe": True,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 变体 9: plugin_config —— 插件配置（PluginInstanceConfig 多实例）
# ---------------------------------------------------------------------

def variant_plugin_config() -> dict[str, Any]:
    """扩展 PluginConfig 含 4 个插件实例，覆盖 enabled/disabled 混合。

    验证：PluginConfig.Data.ConfigRaw 密文字段不被解密为明文落盘；
    PluginScript 在 NativeConfigFacade 中 readable but writable=False。
    """
    corpus = _base_corpus()
    plugin = corpus["PluginConfig.json"]  # type: ignore[index]
    instances = plugin["SubConfigsInfo"]["PluginInstances"]  # type: ignore[index]
    # 添加 2 个额外插件实例
    new_uid_3 = "00000000-0000-0000-0000-000000000003"
    new_uid_4 = "00000000-0000-0000-0000-000000000004"
    instances["instances"].append({"uid": new_uid_3, "type": "PluginInstanceConfig"})  # type: ignore[index]
    instances["instances"].append({"uid": new_uid_4, "type": "PluginInstanceConfig"})  # type: ignore[index]
    instances[new_uid_3] = {  # type: ignore[index]
        "Info": {"Plugin": "third_plugin", "Id": "xyz99", "Enabled": True, "Name": "插件 3"},
        "Data": {
            "ConfigRaw": encrypt_config_value(
                _SAFE_PLAINTEXT_BY_FIELD["ConfigRaw"]
            )
        },
    }
    instances[new_uid_4] = {  # type: ignore[index]
        "Info": {"Plugin": "fourth_plugin", "Id": "def00", "Enabled": False, "Name": "插件 4"},
        "Data": {
            "ConfigRaw": encrypt_config_value(
                _SAFE_PLAINTEXT_BY_FIELD["ConfigRaw"]
            )
        },
    }
    return {
        "name": "plugin_config",
        "description": "PluginConfig 含 4 个插件实例（enabled/disabled 混合，ConfigRaw 为密文）",
        "expect_upgrade": True,
        "expect_load_current": True,
        "expect_roundtrip_equivalent": True,
        "expect_no_plaintext_on_disk": True,
        "expect_pluginscript_writable_false": True,
        "corpus": corpus,
    }


# ---------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------

ALL_VARIANTS = (
    variant_normal,
    variant_missing_fields,
    variant_legacy_aliases,
    variant_garbled_json,
    variant_encrypted_fields,
    variant_redacted_ciphertext,
    variant_partial_write,
    variant_conflicting_uids,
    variant_cross_root_reference,
    variant_plugin_config,
)

VARIANT_NAMES = tuple(
    factory.__name__.removeprefix("variant_") for factory in ALL_VARIANTS
)


def build_all_variants() -> list[dict[str, Any]]:
    """返回 9 类语料的完整描述，每个含 name/description/expect_*/corpus。"""
    return [factory() for factory in ALL_VARIANTS]


def write_corpus_to_dir(
    corpus: Mapping[str, object],
    config_dir,
) -> None:
    """把 corpus 写入 config_dir（每个根一个 JSON 文件）。

    支持 dict（用 json.dumps 序列化）和 bytes（直接写）两种 value 类型。
    成功路径只写入 package-local fake DPAPI 生成的无敏感测试密文；原始
    脱敏占位符仅用于 fail-closed 负例。
    """
    from pathlib import Path

    config_path = Path(config_dir)
    config_path.mkdir(parents=True, exist_ok=True)
    for file_name, value in corpus.items():
        target = config_path / file_name
        if isinstance(value, (bytes, bytearray)):
            target.write_bytes(bytes(value))
        elif isinstance(value, str):
            target.write_text(value, encoding="utf-8")
        else:
            target.write_text(
                json.dumps(value, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )


__all__ = [
    "ALL_VARIANTS",
    "VARIANT_NAMES",
    "build_all_variants",
    "write_corpus_to_dir",
    "variant_normal",
    "variant_missing_fields",
    "variant_legacy_aliases",
    "variant_garbled_json",
    "variant_encrypted_fields",
    "variant_redacted_ciphertext",
    "variant_partial_write",
    "variant_conflicting_uids",
    "variant_cross_root_reference",
    "variant_plugin_config",
]
