#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""Wheelhouse snapshot drift verifier.

确保 ``res/integration-snapshot.json`` 的 ``wheelhouse_contract`` 与指定 wheelhouse
保持一致。默认检查工作树的 ``plugins/wheels``；构建或冻结产物必须通过
``--wheelhouse`` 显式传入，避免把源码树候选与发布快照混为一谈。

使用方式:
    python scripts/verify_wheelhouse_snapshot.py [--repository-root <path>]
        [--wheelhouse <path>] [--strict]

退出码:
    0 = 所有契约字段一致
    1 = 发现漂移或读取失败
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT_MARKER = "pyproject.toml"
SNAPSHOT_RELATIVE_PATH = Path("res") / "integration-snapshot.json"
WHEELS_RELATIVE_PATH = Path("plugins") / "wheels"
MANIFEST_FILENAME = "manifest.json"
RUNTIME_LOCK_FILENAME = "runtime-lock.json"
WHEEL_SUFFIX = ".whl"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class SnapshotDriftError(Exception):
    """Snapshot 与实际 wheelhouse 不一致时抛出。"""


def _read_json_with_optional_bom(path: Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_wheels(wheels_dir: Path) -> int:
    if not wheels_dir.is_dir():
        return 0
    return sum(1 for entry in wheels_dir.iterdir() if entry.is_file() and entry.name.endswith(WHEEL_SUFFIX))


def _resolve_repository_root(repository_root: Path | None) -> Path:
    if repository_root is not None:
        repository_root = repository_root.resolve()
        if not (repository_root / REPO_ROOT_MARKER).is_file():
            raise SnapshotDriftError(
                f"指定的 repository_root 不是宿主根目录: {repository_root}"
            )
        return repository_root
    current = Path(__file__).resolve().parent.parent
    if not (current / REPO_ROOT_MARKER).is_file():
        raise SnapshotDriftError(
            f"无法定位宿主根目录，请通过 --repository-root 显式指定: {current}"
        )
    return current


def _resolve_wheelhouse(repo: Path, wheelhouse: Path | None) -> Path:
    """解析待校验 wheelhouse，允许检查仓库外的冻结构建快照。"""
    resolved = (repo / WHEELS_RELATIVE_PATH) if wheelhouse is None else wheelhouse
    resolved = resolved.resolve()
    if not resolved.is_dir():
        raise SnapshotDriftError(f"wheelhouse 目录缺失: {resolved}")
    return resolved


def _normalized_distribution_name(value: Any) -> str:
    return re.sub(r"[-_.]+", "-", str(value or "").strip().lower())


# ── Lane 13: pyproject.toml [tool.auto-mas.plugin-bootstrap] pin 解析 ──
# 与 pluginBootstrapService.ts 的 loadDeclaredPackageSpecs 行为一致：
# 仅支持 packages 数组中的字符串与 inline table 写法，不引入完整 TOML 依赖。
# 解析失败时不抛错，只返回空列表；调用方决定是否在严格模式下记入 mismatch。
PYPROJECT_BOOTSTRAP_SECTION = "[tool.auto-mas.plugin-bootstrap]"


def _parse_pyproject_bootstrap_packages(pyproject_path: Path) -> list[dict[str, str | None]]:
    """解析 pyproject.toml 的 [tool.auto-mas.plugin-bootstrap].packages。

    Returns:
        list[dict]: 每项形如 ``{"name": str, "version": str|None, "specifier": str|None}``。
        文件缺失或无该 section 时返回空列表。
    """
    if not pyproject_path.is_file():
        return []
    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return []

    marker_index = content.find(PYPROJECT_BOOTSTRAP_SECTION)
    if marker_index < 0:
        return []
    rest = content[marker_index + len(PYPROJECT_BOOTSTRAP_SECTION):]
    # 找到下一个 section 起始 ([xxx])，截断当前 section 主体
    next_section = re.search(r"(?m)^\s*\[[^\]]+\]\s*$", rest)
    section_body = rest[: next_section.start()] if next_section else rest

    packages_match = re.search(r"(?ms)^\s*packages\s*=\s*\[(.*?)\]", section_body)
    if not packages_match:
        return []
    array_body = packages_match.group(1)

    # 按顶层逗号拆分（忽略 { } / 引号内的逗号）
    items: list[str] = []
    current: list[str] = []
    brace_depth = 0
    in_single = False
    in_double = False
    escaping = False
    for ch in array_body:
        if escaping:
            current.append(ch)
            escaping = False
            continue
        if (in_single or in_double) and ch == "\\":
            current.append(ch)
            escaping = True
            continue
        if not in_single and ch == '"':
            in_double = not in_double
            current.append(ch)
            continue
        if not in_double and ch == "'":
            in_single = not in_single
            current.append(ch)
            continue
        if not in_single and not in_double:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == "," and brace_depth == 0:
                token = "".join(current).strip()
                if token:
                    items.append(token)
                current = []
                continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)

    result: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for raw_item in items:
        item = raw_item.strip()
        if not item:
            continue
        # 字符串形式："package-name"
        if (item.startswith('"') and item.endswith('"')) or (
            item.startswith("'") and item.endswith("'")
        ):
            name = _decode_toml_string_literal(item).strip()
            if not name:
                continue
            key = _normalized_distribution_name(name)
            if key in seen:
                continue
            seen.add(key)
            result.append({"name": name, "version": None, "specifier": None})
            continue
        # inline table 形式：{ name = "...", version = "...", specifier = "..." }
        if item.startswith("{") and item.endswith("}"):
            body = item[1:-1].strip()
            fields: dict[str, str] = {}
            for field_token in _split_inline_table_fields(body):
                eq = field_token.find("=")
                if eq <= 0:
                    continue
                k = field_token[:eq].strip()
                v = field_token[eq + 1:].strip()
                if k and v:
                    fields[k] = _decode_toml_string_literal(v)
            name = (fields.get("name") or "").strip()
            if not name:
                continue
            key = _normalized_distribution_name(name)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "name": name,
                    "version": fields.get("version") or None,
                    "specifier": fields.get("specifier") or None,
                }
            )
    return result


def _split_inline_table_fields(body: str) -> list[str]:
    """拆分 inline table 顶层字段（同 splitTopLevelArrayItems 简化版）"""
    items: list[str] = []
    current: list[str] = []
    brace_depth = 0
    in_single = False
    in_double = False
    escaping = False
    for ch in body:
        if escaping:
            current.append(ch)
            escaping = False
            continue
        if (in_single or in_double) and ch == "\\":
            current.append(ch)
            escaping = True
            continue
        if not in_single and ch == '"':
            in_double = not in_double
            current.append(ch)
            continue
        if not in_double and ch == "'":
            in_single = not in_single
            current.append(ch)
            continue
        if not in_single and not in_double:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == "," and brace_depth == 0:
                token = "".join(current).strip()
                if token:
                    items.append(token)
                current = []
                continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _decode_toml_string_literal(raw: str) -> str:
    value = raw.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        inner = value[1:-1]
        return (
            inner
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace("\\\\", "\\")
            .strip()
        )
    return value


def _compare_pyproject_pin_with_runtime_lock(
    pyproject_path: Path, runtime_lock: dict[str, Any]
) -> list[str]:
    """Lane 13: 校验 pyproject plugin-bootstrap pin 与 runtime-lock plugin version 一致。

    - 仅对 pyproject 中显式声明 version 的包做严格匹配；specifier 形式的包跳过
      （与 pluginBootstrapService.isVersionAllowed 行为一致，specifier 用范围匹配，
      无法用相等比较直接判定漂移；这里只做"pin 不应滞后/超前于 lock"的精确检测）。
    - 对 runtime-lock 中存在但 pyproject 未声明的包：跳过（runtime 依赖可能在
      wheelhouse 中但不需要被 pyproject 显式声明）。
    """
    mismatches: list[str] = []
    declared = _parse_pyproject_bootstrap_packages(pyproject_path)
    if not declared:
        return mismatches  # pyproject 不在或 section 缺失：留给上层判断

    plugins = runtime_lock.get("plugins") if isinstance(runtime_lock, dict) else None
    if not isinstance(plugins, list):
        mismatches.append(
            "runtime-lock.plugins 不是列表；无法与 pyproject plugin-bootstrap pin 比对"
        )
        return mismatches

    lock_by_name: dict[str, str] = {}
    for entry in plugins:
        if not isinstance(entry, dict):
            continue
        name = _normalized_distribution_name(entry.get("distribution"))
        version = str(entry.get("version") or "").strip()
        if name and version:
            lock_by_name[name] = version

    for pkg in declared:
        name = _normalized_distribution_name(pkg.get("name") or "")
        if not name:
            continue
        pinned_version = pkg.get("version")
        if not pinned_version:
            # 仅包名或 specifier 形式：交给运行时 specifier 匹配；此处不强制相等
            continue
        lock_version = lock_by_name.get(name)
        if lock_version is None:
            mismatches.append(
                f"pyproject plugin-bootstrap 声明 {name}=={pinned_version}，"
                f"但 runtime-lock.plugins 中找不到该 distribution"
            )
            continue
        if lock_version != pinned_version:
            mismatches.append(
                f"pyproject plugin-bootstrap pin 与 runtime-lock 不一致: "
                f"distribution={name}, pyproject_pin={pinned_version!r}, "
                f"runtime_lock_version={lock_version!r}"
            )
    return mismatches


def verify_wheelhouse_snapshot(
    repository_root: Path | None = None,
    *,
    wheelhouse: Path | None = None,
) -> dict[str, Any]:
    """校验 integration-snapshot.json 与实际 wheelhouse 是否一致。

    Returns:
        dict: 包含 snapshot 路径、wheels 路径和各项校验结果。

    Raises:
        SnapshotDriftError: 任一契约字段与实际值不一致时抛出。
    """
    repo = _resolve_repository_root(repository_root)
    snapshot_path = repo / SNAPSHOT_RELATIVE_PATH

    if not snapshot_path.is_file():
        raise SnapshotDriftError(f"integration-snapshot.json 缺失: {snapshot_path}")

    wheels_dir = _resolve_wheelhouse(repo, wheelhouse)
    manifest_path = wheels_dir / MANIFEST_FILENAME
    runtime_lock_path = wheels_dir / RUNTIME_LOCK_FILENAME
    if not manifest_path.is_file():
        raise SnapshotDriftError(f"manifest.json 缺失: {manifest_path}")
    if not runtime_lock_path.is_file():
        raise SnapshotDriftError(f"runtime-lock.json 缺失: {runtime_lock_path}")

    snapshot = _read_json_with_optional_bom(snapshot_path)
    contract = snapshot.get("wheelhouse_contract") if isinstance(snapshot, dict) else None
    if not isinstance(contract, dict):
        raise SnapshotDriftError("integration-snapshot.json 缺少 wheelhouse_contract 对象")

    manifest = _read_json_with_optional_bom(manifest_path)
    runtime_lock = _read_json_with_optional_bom(runtime_lock_path)
    if not isinstance(manifest, dict):
        raise SnapshotDriftError("manifest.json 顶层不是对象")
    if not isinstance(runtime_lock, dict):
        raise SnapshotDriftError("runtime-lock.json 顶层不是对象")

    mismatches: list[str] = []

    expected_manifest_schema = contract.get("manifest_schema_version")
    if manifest.get("schema_version") != expected_manifest_schema:
        mismatches.append(
            f"manifest.schema_version 期望 {expected_manifest_schema}, 实际 {manifest.get('schema_version')}"
        )

    expected_runtime_lock_schema = contract.get("runtime_lock_schema_version")
    if runtime_lock.get("schema_version") != expected_runtime_lock_schema:
        mismatches.append(
            f"runtime-lock.schema_version 期望 {expected_runtime_lock_schema}, 实际 {runtime_lock.get('schema_version')}"
        )

    expected_wheel_count = contract.get("wheel_count")
    if not isinstance(expected_wheel_count, int) or expected_wheel_count <= 0:
        mismatches.append(f"wheelhouse_contract.wheel_count 非法: {expected_wheel_count!r}")
    else:
        actual_wheel_count = _count_wheels(wheels_dir)
        if actual_wheel_count != expected_wheel_count:
            mismatches.append(
                f"wheel_count 期望 {expected_wheel_count}, 实际 {actual_wheel_count}"
            )

    expected_plugin_count = contract.get("plugin_distribution_count")
    if not isinstance(expected_plugin_count, int) or expected_plugin_count <= 0:
        mismatches.append(
            f"wheelhouse_contract.plugin_distribution_count 非法: {expected_plugin_count!r}"
        )
    else:
        plugins = runtime_lock.get("plugins")
        if not isinstance(plugins, list):
            mismatches.append("runtime-lock.plugins 不是列表")
        elif len(plugins) != expected_plugin_count:
            mismatches.append(
                f"plugin_distribution_count 期望 {expected_plugin_count}, 实际 {len(plugins)}"
            )

    expected_entry_point_count = contract.get("plugin_entry_point_count")
    if not isinstance(expected_entry_point_count, int) or expected_entry_point_count <= 0:
        mismatches.append(
            f"wheelhouse_contract.plugin_entry_point_count 非法: {expected_entry_point_count!r}"
        )
    else:
        entry_points = runtime_lock.get("expected_plugin_entry_points")
        if not isinstance(entry_points, list):
            mismatches.append("runtime-lock.expected_plugin_entry_points 不是列表")
        elif len(entry_points) != expected_entry_point_count:
            mismatches.append(
                f"plugin_entry_point_count 期望 {expected_entry_point_count}, 实际 {len(entry_points)}"
            )

    expected_core_version = str(contract.get("core_distribution_version") or "").strip()
    if not expected_core_version:
        mismatches.append("wheelhouse_contract.core_distribution_version 缺失")
    else:
        plugins = runtime_lock.get("plugins")
        core_versions = [
            str(item.get("version") or "").strip()
            for item in plugins or []
            if isinstance(item, dict)
            and _normalized_distribution_name(item.get("distribution")) == "auto-mas-core"
        ] if isinstance(plugins, list) else []
        if len(core_versions) != 1:
            mismatches.append(
                "runtime-lock.plugins 必须恰好包含一个 auto-mas-core，"
                f"实际版本项={core_versions}"
            )
        elif core_versions[0] != expected_core_version:
            mismatches.append(
                f"core_distribution_version 期望 {expected_core_version}, 实际 {core_versions[0]}"
            )

    expected_manifest_sha = str(contract.get("manifest_sha256") or "")
    if not SHA256_PATTERN.match(expected_manifest_sha):
        mismatches.append(f"wheelhouse_contract.manifest_sha256 非法: {expected_manifest_sha!r}")
    else:
        actual_manifest_sha = _sha256_file(manifest_path)
        if actual_manifest_sha.lower() != expected_manifest_sha.lower():
            mismatches.append(
                f"manifest_sha256 期望 {expected_manifest_sha.lower()}, 实际 {actual_manifest_sha.lower()}"
            )

    expected_runtime_lock_sha = str(contract.get("runtime_lock_sha256") or "")
    if not SHA256_PATTERN.match(expected_runtime_lock_sha):
        mismatches.append(
            f"wheelhouse_contract.runtime_lock_sha256 非法: {expected_runtime_lock_sha!r}"
        )
    else:
        actual_runtime_lock_sha = _sha256_file(runtime_lock_path)
        if actual_runtime_lock_sha.lower() != expected_runtime_lock_sha.lower():
            mismatches.append(
                f"runtime_lock_sha256 期望 {expected_runtime_lock_sha.lower()}, 实际 {actual_runtime_lock_sha.lower()}"
            )

    # Lane 13 P0: pyproject plugin-bootstrap pin ↔ runtime-lock plugin version 一致性
    # 当 pyproject.toml 在宿主根目录可见时做严格匹配；缺失则不报错（适配 --wheelhouse
    # 指向独立 wheelhouse 但 pyproject 不在场的情况，例如对冻结 r6 单独校验）。
    pyproject_path = repo / "pyproject.toml"
    if pyproject_path.is_file():
        pin_mismatches = _compare_pyproject_pin_with_runtime_lock(pyproject_path, runtime_lock)
        mismatches.extend(pin_mismatches)

    if mismatches:
        raise SnapshotDriftError(
            "integration-snapshot.json 与实际 wheelhouse 不一致:\n- " + "\n- ".join(mismatches)
        )

    return {
        "repository_root": str(repo),
        "snapshot_path": str(snapshot_path),
        "wheels_dir": str(wheels_dir),
        "wheel_count": _count_wheels(wheels_dir),
        "plugin_distribution_count": len(runtime_lock.get("plugins") or []) if isinstance(runtime_lock.get("plugins"), list) else 0,
        "entry_point_count": len(runtime_lock.get("expected_plugin_entry_points") or []) if isinstance(runtime_lock.get("expected_plugin_entry_points"), list) else 0,
        "core_distribution_version": core_versions[0] if len(core_versions) == 1 else None,
        "manifest_sha256": _sha256_file(manifest_path),
        "runtime_lock_sha256": _sha256_file(runtime_lock_path),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="校验 integration-snapshot.json 与 plugins/wheels 实际内容是否一致。"
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help="宿主根目录（包含 pyproject.toml 的目录）。省略时自动从脚本位置推断。",
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        default=None,
        help="待校验 wheelhouse 目录；省略时检查 <repository-root>/plugins/wheels。",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：任何警告也视为错误（当前等价于默认行为，保留以兼容未来扩展）。",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = verify_wheelhouse_snapshot(
            args.repository_root,
            wheelhouse=args.wheelhouse,
        )
    except SnapshotDriftError as error:
        print(f"[verify_wheelhouse_snapshot] 失败: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - 顶层兜底，避免 traceback 污染 CI 日志
        print(f"[verify_wheelhouse_snapshot] 异常: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(
        "[verify_wheelhouse_snapshot] 通过: "
        f"wheels={result['wheel_count']}, "
        f"plugins={result['plugin_distribution_count']}, "
        f"entry_points={result['entry_point_count']}, "
        f"core={result['core_distribution_version']}, "
        f"manifest_sha256={result['manifest_sha256'][:12]}..., "
        f"runtime_lock_sha256={result['runtime_lock_sha256'][:12]}..."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
