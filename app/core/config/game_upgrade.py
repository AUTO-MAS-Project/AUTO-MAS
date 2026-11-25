"""旧设备与 MAS 管理的客户端路径一次性转换为游戏对象和账号绑定。"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config.types import normalize_path_input
from app.utils import io

RECORD = ".game-migration-v1.json"
PLUGINS = {
    "mumu": ("mumu_adapter", "auto-mas-mumu-adapter", "MuMuGame", "MuMuDevice"),
    "ldplayer": (
        "ldplayer_adapter",
        "auto-mas-ldplayer-adapter",
        "LDPlayerGame",
        "LDPlayerDevice",
    ),
    "avd": (
        "mod_avd_adapter",
        "auto-mas-mod-avd-adapter",
        "ModAvdGame",
        "ModAvdDevice",
    ),
    "general": (
        "general_emulator_adapter",
        "auto-mas-general-emulator-adapter",
        "GeneralGame",
        "GeneralDevice",
    ),
    "client": (
        "win_process_adapter",
        "auto-mas-win-process-adapter",
        "WinProcessGame",
        "WinProcessDevice",
    ),
}
DEFAULT_GAME_PLUGINS = tuple(
    PLUGINS[kind][:2] for kind in ("mumu", "ldplayer", "general", "client")
)


def _entries(document):
    data = document.get("data", document)
    for item in document.get("order", document.get("instances", [])):
        yield str(item["uid"]), item["type"], data[str(item["uid"])]


def _users(script):
    nested = script.get("SubConfigsInfo", {})
    return script.get(
        "users", script.get("UserData", nested.get("users", nested.get("UserData", {})))
    )


def _list(value):
    return json.loads(value) if isinstance(value, str) else value or []


def _document(root: Path, stem: str, legacy: str):
    for name in (stem + ".yaml", legacy + ".json"):
        path = root / name
        if path.is_file():
            return io.read_dict_file(path)
    return {"order": [], "data": {}}


def required_game_plugins(root: Path) -> dict[str, str]:
    kinds: set[str] = set()
    complete = (root / RECORD).exists() and io.read_dict_file(root / RECORD).get(
        "complete"
    )
    legacy_devices = (
        {"order": [], "data": {}}
        if complete
        else _document(root, "emulators", "EmulatorConfig")
    )
    for _, _, raw in _entries(legacy_devices):
        info = raw.get("Info", raw.get("Data", {}))
        if info.get("Type") == "emulator2":
            kinds.update(p["type"] for p in _list(info.get("Paths")))
        else:
            kinds.add(info.get("Type", "general"))
    for _, name, _ in _entries(_document(root, "games", "games")):
        kinds.update(kind for kind, values in PLUGINS.items() if values[2] == name)
    # 客户端对象来自 MAS 自己保存的配置；不扫描系统进程或任意硬盘目录。
    for _, kind, script in _entries(
        {"order": [], "data": {}}
        if complete
        else _document(root, "scripts", "ScriptConfig")
    ):
        if _client_path(kind, script):
            kinds.add("client")
        for _, _, user in _entries(_users(script)):
            if _client_path(kind, script, user):
                kinds.add("client")
    return {PLUGINS[k][0]: PLUGINS[k][1] for k in kinds}


def _client_path(kind: str, script: dict, user: dict | None = None) -> str | None:
    game = script.get("Game", {})
    if user is not None:
        if kind == "BetterGIConfig":
            return user.get("Switch", {}).get("GamePath") or None
        if kind == "ZzzOdConfig":
            return user.get("Game", {}).get("GamePath") or None
        return None
    if kind == "ZzzOdConfig":
        return game.get("Path") or None
    if kind in {"MaaFWConfig", "M9AConfig", "MSSConfig"}:
        return game.get("LaunchPath") or None
    if kind == "GeneralConfig" and game.get("Type") in {"Emulator", "URL"}:
        return None
    if kind == "HSRConfig" and game.get("Platform") == "Cloud":
        return None
    if kind == "OkwwConfig":
        return game.get("ClientPath") or game.get("Path") or None
    if kind in {"GeneralConfig", "MaaEndConfig", "HSRConfig", "OkNteConfig"}:
        return game.get("Path") or None
    return None


def _client_info(kind, script, path):
    """只转换 MAS 保存的路径，复用现有官方启动器定位器。"""
    game = script.get("Game", {})
    executable = normalize_path_input(path)
    if executable is None:
        raise ValueError("原游戏路径无法解析，请重新选择游戏目标")
    launcher = game.get("LauncherPath")
    if kind == "HSRConfig" and executable.suffix.casefold() != ".exe":
        executable /= "StarRail.exe"
    elif kind == "OkwwConfig":
        launcher = game.get("Path")
        if not game.get("ClientPath") and launcher:
            from app.services import wuthering_waves

            executable = wuthering_waves.resolve_wuthering_waves_process_path(
                Path(launcher)
            )
    elif kind == "OkNteConfig" and executable.name.casefold() != "htgame.exe":
        launcher = str(executable)
        # 官方安装把 Client 与 NTELauncher 放在同一安装根下，不按全盘或进程名猜测。
        install = (
            executable.parent.parent
            if executable.parent.name.casefold() == "ntelauncher"
            else executable.parent
        )
        candidates = (
            list((install / "Client").rglob("HTGame.exe"))
            if (install / "Client").is_dir()
            else []
        )
        if len(candidates) != 1:
            raise ValueError(
                "无法从异环启动器确定唯一客户端路径，请在游戏管理中重新选择客户端"
            )
        executable = candidates[0]
    arguments = game.get("Arguments") or ""
    return {
        "name": executable.stem,
        "type": "client",
        "concurrent_execution": False,
        "path": str(executable),
        "launch_path": launcher,
        "launch_with_launcher": kind != "OkwwConfig" or game.get("Type") == "Launcher",
        "arguments": arguments
        if isinstance(arguments, list)
        else shlex.split(arguments, posix=False),
    }


def _identity(path: str) -> str:
    resolved = normalize_path_input(path)
    if resolved is None:
        raise ValueError("原路径无法解析，请重新选择游戏目标")
    return os.path.normcase(str(resolved))


def _client_launch_identity(info: dict) -> tuple[list[str], bool | None, str | None]:
    launcher = normalize_path_input(info.get("launch_path"))
    return (
        info.get("arguments", []),
        info.get("launch_with_launcher"),
        os.path.normcase(str(launcher)) if launcher is not None else None,
    )


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate_game_documents(
    root: Path,
    *,
    resolve_installation: Mapping[str, Callable[[str], str | None]] | None = None,
) -> None:
    """先落盘游戏对象，再转换绑定；中断沿用原件及确定身份，不重复创建。"""
    record_path = root / RECORD
    record = io.read_dict_file(record_path) if record_path.exists() else {}
    if record.get("complete"):
        return
    backup = root / "legacy-game"
    backup.mkdir(parents=True, exist_ok=True)
    script_name = record.get("script_source") or (
        "scripts.yaml"
        if (root / "scripts.yaml").exists() or not (root / "ScriptConfig.json").exists()
        else "ScriptConfig.json"
    )
    record["script_source"] = script_name
    for name in (
        "scripts.yaml",
        "emulators.yaml",
        "games.yaml",
        "ScriptConfig.json",
        "EmulatorConfig.json",
    ):
        source = root / name
        if source.exists() and not (backup / name).exists():
            io.atomic_write(backup / name, source.read_bytes())
    scripts = _document(backup, "scripts", "ScriptConfig")
    emulators = _document(backup, "emulators", "EmulatorConfig")
    games = _document(root, "games", "games")
    games = deepcopy(games)
    games.setdefault("order", [])
    games.setdefault("data", {})
    diagnostics = []
    mapping = {}

    def add_game(kind, uid, info):
        tag = PLUGINS[kind][2]
        path = info.get("path")
        canonical = _identity(path) if path else None
        launch = _client_launch_identity(info) if kind == "client" else None
        for other_uid, other_kind, other in _entries(games):
            other_info = other.get("info", {})
            if (
                other_kind == tag
                and canonical
                and other_info.get("path")
                and _identity(other_info["path"]) == canonical
                and (launch is None or _client_launch_identity(other_info) == launch)
            ):
                return other_uid
        uid = str(uid)
        if uid in games["data"]:
            existing = games["data"][uid]
            if existing.get("info", {}).get("path") != path:
                raise ValueError(f"游戏迁移目标冲突：{uid}")
            return uid
        games["order"].append({"uid": uid, "type": tag})
        games["data"][uid] = {"info": info, "devices": {"order": [], "data": {}}}
        return uid

    def add_device(game_uid, kind, native, slot, *, tombstone=False, extra=None):
        game = games["data"][game_uid]
        devices = game.setdefault("devices", {"order": [], "data": {}})
        uid = str(
            uuid5(UUID(game_uid), "client" if kind == "client" else f"{native}:{slot}")
        )
        if uid not in devices["data"]:
            devices["order"].append({"uid": uid, "type": PLUGINS[kind][3]})
            info = {"name": game["info"]["name"], "status": 1}
            if kind != "client":
                info.update(
                    index=str(native),
                    slot=int(slot),
                    tombstone=tombstone,
                    adb_address="",
                )
            info.update(extra or {})
            devices["data"][uid] = {"info": info}
        return uid

    # 保存旧模拟器的实际引用，避免首次发现前丢掉离线实例身份。
    referenced: dict[str, set[str]] = {}
    for _, _, script in _entries(scripts):
        for owner in [script, *(u for _, _, u in _entries(_users(script)))]:
            group = owner.get("Emulator", {})
            game = owner.get("Game", {})
            emulator_id = str(group.get("Id", game.get("EmulatorId", "-")))
            index = str(group.get("Index", game.get("EmulatorIndex", "-")))
            if emulator_id != "-" and index not in {"", "-"}:
                referenced.setdefault(emulator_id, set()).add(index)

    for old_uid, _, raw in _entries(emulators):
        info = raw.get("Info", raw.get("Data", {}))
        kind = info.get("Type", "general")
        paths = (
            _list(info.get("Paths"))
            if kind == "emulator2"
            else [
                {
                    "pathId": old_uid,
                    "type": kind,
                    "installPath": info.get("Path"),
                    "alias": info.get("Name", "模拟器"),
                }
            ]
        )
        slots = _list(info.get("Slots")) if kind == "emulator2" else []
        path_games = {}
        for path in paths:
            actual = path["type"]
            if actual not in PLUGINS or actual == "client":
                raise ValueError(f"尚未支持的旧模拟器类型：{actual}")
            proposed = (
                UUID(old_uid)
                if len(paths) == 1
                else uuid5(UUID(old_uid), str(path["pathId"]))
            )
            manager = path.get("installPath")
            resolver = (resolve_installation or {}).get(PLUGINS[actual][2])
            if manager and resolver is not None:
                manager = resolver(str(manager)) or manager
            game_uid = add_game(
                actual,
                proposed,
                {
                    "name": path.get("alias") or info.get("Name", "模拟器"),
                    "type": "emulator",
                    "concurrent_execution": True,
                    "path": manager,
                    "max_wait_time": info.get("MaxWaitTime", 300),
                    "stable_mode": info.get("StableMode", False),
                    "config_guard": info.get("ConfigGuard", False),
                    "force_kill_before_launch": info.get(
                        "ForceKillBeforeLaunch", False
                    ),
                    "force_kill_on_close": info.get("ForceKillOnClose", False),
                    "boss_key": _list(info.get("BossKey")),
                },
            )
            path_games[str(path["pathId"])] = (game_uid, actual)
        if kind == "emulator2":
            for slot in slots:
                key = str(slot["slot"])
                target = path_games.get(str(slot.get("pathId", "")))
                if target is None:
                    # 完全退役的槽位没有真实归属；在每条安装保留墓碑，防止重用旧号。
                    if slot.get("state") == "tombstone":
                        for game_uid, actual in path_games.values():
                            add_device(
                                game_uid, actual, "", slot["slot"], tombstone=True
                            )
                    continue
                game_uid, actual = target
                device_uid = add_device(
                    game_uid,
                    actual,
                    slot["nativeIndex"],
                    slot["slot"],
                    tombstone=slot.get("state") == "tombstone",
                )
                mapping[(old_uid, key)] = (game_uid, device_uid)
        elif path_games:
            game_uid, actual = next(iter(path_games.values()))
            for position, index in enumerate(sorted(referenced.get(old_uid, []))):
                native = index
                extra = {}
                if actual == "general":
                    if "|" not in index:
                        continue  # 绑定阶段标记失效，其他托管仍可迁移。
                    args, address = index.rsplit("|", 1)
                    address = address.strip().replace("：", ":").replace("。", ".")
                    if not address:
                        continue
                    try:
                        arguments = shlex.split(args)
                    except ValueError:
                        continue
                    extra = {
                        "arguments": arguments,
                        "adb_address": address,
                    }
                device_uid = add_device(game_uid, actual, native, position, extra=extra)
                mapping[(old_uid, index)] = (game_uid, device_uid)

    def bind(owner, script, script_type, source):
        previous = owner.get("game", {})
        if previous.get("game_id") not in {None, "-"}:
            return
        emulator = owner.get("Emulator", {})
        game = owner.get("Game", {})
        old_uid = str(emulator.get("Id", game.get("EmulatorId", "-")))
        old_index = str(emulator.get("Index", game.get("EmulatorIndex", "-")))
        client_path = _client_path(
            script_type, script, owner if owner is not script else None
        )
        if old_uid != "-" and not client_path:
            target = mapping.get((old_uid, old_index))
            if target is None:
                reason = f"原设备不可用：{old_uid}/{old_index}"
                owner["game"] = {
                    "game_id": "-",
                    "device_id": "-",
                    "unavailable_reason": reason,
                }
                diagnostics.append({"source": source, "reason": reason})
            else:
                owner["game"] = {"game_id": target[0], "device_id": target[1]}
        elif client_path:
            try:
                info = _client_info(script_type, script, client_path)
            except (OSError, ValueError, RuntimeError) as error:
                reason = str(error)
                owner["game"] = {
                    "game_id": "-",
                    "device_id": "-",
                    "unavailable_reason": reason,
                }
                diagnostics.append({"source": source, "reason": reason})
                return
            identity = (_identity(info["path"]), *_client_launch_identity(info))
            uid = uuid5(NAMESPACE_URL, "auto-mas:client:" + json.dumps(identity))
            game_uid = add_game(
                "client",
                uid,
                info,
            )
            device_uid = add_device(game_uid, "client", "client", 0)
            owner["game"] = {"game_id": game_uid, "device_id": device_uid}
        # 旧设备字段只参与本次转换，普通运行只读取 game。
        owner.pop("Emulator", None)
        if isinstance(owner.get("Game"), dict):
            owner["Game"].pop("EmulatorId", None)
            owner["Game"].pop("EmulatorIndex", None)

    for sid, script_type, script in _entries(scripts):
        old_info = script.get("info", {})
        if old_info.get("game_id") not in {None, "-"}:
            script["game"] = {
                "game_id": old_info.pop("game_id"),
                "device_id": old_info.pop("game_device_id", "-"),
            }
        bind(script, script, script_type, sid)
        for uid, _, user in _entries(_users(script)):
            bind(user, script, script_type, f"{sid}/{uid}")

    # 配置守卫基准随稳定设备 UID 转换，不能丢掉用户明确保存的设置。
    for old_uid, _, raw in _entries(emulators):
        baselines = raw.get("Info", raw.get("Data", {})).get("Baselines", {})
        baselines = json.loads(baselines) if isinstance(baselines, str) else baselines
        for index, values in baselines.items():
            target = mapping.get((old_uid, str(index)))
            if target is not None:
                games["data"][target[0]]["info"].setdefault("baselines", {})[
                    target[1]
                ] = values

    record.update(
        {
            "version": 1,
            "diagnostics": diagnostics,
            "mapping": {
                f"{uid}/{index}": list(target)
                for (uid, index), target in mapping.items()
            },
        }
    )
    io.write_file(record_path, record)
    # 文件级原子替换；配置对象始终先于引用写盘，重试使用首次备份与确定 UID。
    for name, payload in (("games.yaml", games), (script_name, scripts)):
        if name == script_name and not (backup / script_name).exists():
            # 空用户目录的脚本文档仍由已有 JSON 升级管道初始化，不能抢先创建未登记目标。
            continue
        output = root / name
        if (
            output.exists()
            and name in record.get("written", {})
            and _hash(output) != record["written"][name]
        ):
            raise ValueError(f"游戏升级目标已被修改，保留文件待处理：{name}")
        io.write_file(output, payload)
        record.setdefault("written", {})[name] = _hash(output)
        io.write_file(record_path, record)
    record["complete"] = True
    io.write_file(record_path, record)
