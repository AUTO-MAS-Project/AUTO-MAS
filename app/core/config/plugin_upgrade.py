"""主程序从内置专项切换至插件实现的一次性配置升级。"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.version import Version

from app.core.config.upgrade import is_blank_file
from app.plugin.types import PluginCodeDrift, PluginState
from app.utils import io as _utils_io

if TYPE_CHECKING:
    from app.models.config import PluginRegistryCollection


# 只列入已经完成插件化的专项；后续专项迁移随对应的数据升级段落扩展。
_ADAPTER_PLUGINS = {
    "BetterGIConfig": ("bettergi_adapter", "auto-mas-bettergi-adapter"),
    "SrcConfig": ("src_adapter", "auto-mas-src-adapter"),
    "WhimboxConfig": ("whimbox_adapter", "auto-mas-whimbox-adapter"),
    "MaaConfig": ("maa_adapter", "auto-mas-maa-adapter"),
    "MaaPluginConfig": ("maa_adapter", "auto-mas-maa-adapter"),
    "MaaPlanConfig": ("maa_adapter", "auto-mas-maa-adapter"),
    "MaaPluginPlanConfig": ("maa_adapter", "auto-mas-maa-adapter"),
    "MaaFWConfig": ("maafw_adapter", "auto-mas-maafw-adapter"),
    "M9AConfig": ("m9a_adapter", "auto-mas-m9a-adapter"),
    "MSSConfig": ("mss_adapter", "auto-mas-mss-adapter"),
    "MSSPlanConfig": ("mss_adapter", "auto-mas-mss-adapter"),
}
# MFW 一族（通用 MFW、M9A、MSS）改由插件提供后，首次接手前备份的托管与计划表类型。
MAAFW_FAMILY_TYPE_NAMES = frozenset(
    {"MaaFWConfig", "M9AConfig", "MSSConfig", "MSSPlanConfig"}
)
MAAFW_FAMILY_PLUGINS = frozenset({"maafw_adapter", "m9a_adapter", "mss_adapter"})
_ADAPTER_PLUGIN_NAMES = frozenset(target[0] for target in _ADAPTER_PLUGINS.values())
# 宿主内置托管要的库：托管类型 → 需求。它们不是插件，不进注册表，只随启动前的共享环境
# 准备装进插件环境；只写下限，和依赖同一个库的插件按各自范围共存。
_HOST_LIBRARIES = {
    # MaaEnd 拼游戏启动设置要用 MFW 的 interface 解析库。
    "MaaEndConfig": "auto-mas-maafw-interface>=0.2.0",
}
_MINIMUM_ADAPTER_VERSIONS = {
    "maa_adapter": Version("0.1.4"),
    "mumu_adapter": Version("0.1.1"),
    "ldplayer_adapter": Version("0.1.1"),
    # 0.3 起插件之间只经宿主的服务调用；0.2.x 的专项直接导入的模块，在 0.3 的服务插件里
    # 已经没有，两代不能混装，所以三个专项的下限提到 0.3.0。
    "maafw_adapter": Version("0.3.0"),
    "m9a_adapter": Version("0.3.0"),
    "mss_adapter": Version("0.3.0"),
}


def adapter_package(config_type: str) -> str | None:
    """已插件化的托管或计划表类型由哪个发行包提供；不认识的类型返回 None。"""
    target = _ADAPTER_PLUGINS.get(config_type)
    return target[1] if target else None


def automatic_plugin_packages(
    required: dict[str, str], registry: PluginRegistryCollection, uninstalled: list[str]
) -> dict[str, str]:
    """已升级的数据只补装首次接手或仍希望启用的插件；发现新包前读取持久意图。"""
    return {
        name: package
        for name, package in required.items()
        if (
            record.info.enabled
            if (record := registry.by_name(name)) is not None
            else name not in uninstalled
        )
    }


def _index_types(config_path: Path) -> list[str]:
    """托管与计划集合索引里各条目的类型名，按文件和条目顺序；不读业务字段。"""
    types = []
    for name in ("ScriptConfig.json", "PlanConfig.json", "scripts.yaml", "plans.yaml"):
        path = config_path / name
        if not path.is_file() or is_blank_file(path):
            continue
        document = _utils_io.read_dict_file(path)
        types.extend(
            item["type"]
            for item in document.get("order", document.get("instances", []))
        )
    return types


def required_adapter_plugins(config_path: Path) -> dict[str, str]:
    """按旧托管及计划索引识别升级所需插件，不扫描备份或业务字段中的字符串。"""
    required = {}
    for kind in _index_types(config_path):
        if target := _ADAPTER_PLUGINS.get(kind):
            required[target[0]] = target[1]
    # v1.8 之前仍按目录保存专项，尚无聚合集合索引。
    if any(config_path.glob("MaaConfig/*/config.json")) or any(
        config_path.glob("MaaPlanConfig/*/config.json")
    ):
        required["maa_adapter"] = "auto-mas-maa-adapter"
    if any(config_path.glob("WhimboxConfig/*/config.json")):
        required["whimbox_adapter"] = "auto-mas-whimbox-adapter"
    if any(config_path.glob("BetterGIConfig/*/config.json")):
        required["bettergi_adapter"] = "auto-mas-bettergi-adapter"
    return required


def required_minimum_versions(config_path: Path) -> dict[str, Version]:
    """存量配置要的专项插件里带版本下限的那些：插件 ID → 下限。

    启动前的共享环境准备按它把低于下限的已装专项（连同同族）升上来；仍没达标的，
    插件管理器这一轮不启用它，免得旧类接手配置。
    """
    return {
        name: _MINIMUM_ADAPTER_VERSIONS[name]
        for name in required_adapter_plugins(config_path)
        if name in _MINIMUM_ADAPTER_VERSIONS
    }


def required_host_libraries(config_path: Path) -> list[str]:
    """配置里的宿主内置托管要装进插件环境的库（需求串）；没有这类托管时为空。"""
    types = set(_index_types(config_path))
    return sorted(
        {requirement for kind, requirement in _HOST_LIBRARIES.items() if kind in types}
    )


# 版本没达标、这一轮不接手配置时给用户看的原因。
BELOW_MINIMUM_RESTART = "新版本已准备好，重启后生效"
BELOW_MINIMUM_FAILED = "插件版本过低，升级没有完成"


async def install_adapter_plugins(required: dict[str, str]) -> None:
    """在领域集合激活前复用插件安装及启用入口，失败时中止配置升级。"""
    for name, package in required.items():
        await install_adapter_plugin(name, package)


async def install_adapter_plugin(name: str, package: str) -> None:
    """确保适配插件已安装、加载并启用。"""
    from app.core import Config, Plugin
    from app.models.config import PluginMeta
    from app.plugin.runtime import discover

    # 本地源码插件不会出现在旧注册表里；先按当前来源发现一次，避免把开发工程当成
    # 未安装而去 PyPI 拉发行包（install 会拒绝与本地工程同名）。
    await discover.refresh()
    record = Config.plugin_registry.by_name(name)
    minimum = _MINIMUM_ADAPTER_VERSIONS.get(name)
    needs_upgrade = (
        minimum is not None
        and record is not None
        and record.info.source == "installed"
        and record.info.version
        and Version(record.info.version) < minimum
    )
    # 专项的旧版本不能接手配置，要等新版代码就绪。
    hold = bool(needs_upgrade) and name in _ADAPTER_PLUGIN_NAMES
    if (
        record is None
        or needs_upgrade
        or record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED
        or record._project_dir is None
        or not (record._project_dir / record.info.import_name).is_dir()
    ):
        try:
            result = await Plugin.install(
                PluginMeta.build(info={"plugin_name": name, "package_name": package}),
                minimum_version=minimum,
            )
        except Exception as error:
            if hold:
                raise RuntimeError(f"{BELOW_MINIMUM_FAILED}：{error}") from error
            raise
        if hold and (result or {}).get("restart_required"):
            # 新版本只在候选目录里，进程里加载的仍是旧版本：不启用、不接手，等重启。
            raise RuntimeError(BELOW_MINIMUM_RESTART)
        record = Config.plugin_registry.by_name(name)
    if record is None:
        raise RuntimeError(f"适配插件安装后未登记：{name}")
    if record._plugin_cls is None:
        await Plugin.load(record)
    if record.info.state != PluginState.ENABLED:
        await Plugin.enable(record)
    if record.info.state != PluginState.ENABLED:
        raise RuntimeError(f"适配插件未启用：{name}")


def backup_legacy_adapter_users(
    config_path: Path, adapter: str, config_type: str
) -> None:
    """首次接手内置托管索引时备份原文件，正文的加载和校验交给配置集合。"""
    for name in ("scripts.yaml", "ScriptConfig.json"):
        path = config_path / name
        backup = config_path / f"legacy-{adapter}-plugin" / name
        if backup.exists() or not path.is_file() or is_blank_file(path):
            continue
        document = _utils_io.read_dict_file(path)
        index = document.get("order", document.get("instances", []))
        if any(item["type"] == config_type for item in index):
            backup.parent.mkdir(parents=True, exist_ok=True)
            _utils_io.atomic_write(backup, path.read_bytes())


def backup_legacy_maafw_documents(config_path: Path) -> None:
    """首次由插件接手 MFW 一族前按字节备份托管与计划表文件；已有备份不覆盖。

    插件类激活后会把账号集合以新形状写回（``UserData`` → ``users``），旧宿主读不了；
    回退到旧宿主时把 ``config/legacy-maafw-plugin/`` 下的文件拷回 ``config/``。
    """
    for name in ("scripts.yaml", "ScriptConfig.json", "plans.yaml", "PlanConfig.json"):
        path = config_path / name
        backup = config_path / "legacy-maafw-plugin" / name
        if backup.exists() or not path.is_file() or is_blank_file(path):
            continue
        document = _utils_io.read_dict_file(path)
        index = document.get("order", document.get("instances", []))
        if any(item["type"] in MAAFW_FAMILY_TYPE_NAMES for item in index):
            backup.parent.mkdir(parents=True, exist_ok=True)
            _utils_io.atomic_write(backup, path.read_bytes())


def prepare_plugin_documents(config_path: Path) -> None:
    """备份并转换插件化前的类型标签与迁移标记，保持 UID、顺序及业务值。"""
    names = {
        "MaaPluginConfig": "MaaConfig",
        "MaaPluginUserConfig": "MaaUserConfig",
        "MaaPluginPlanConfig": "MaaPlanConfig",
    }

    def convert(value):
        """递归只替换集合索引中的旧类型标签，不改用户输入字符串或业务字段。"""
        changed = False
        if isinstance(value, dict):
            for item in value.get("order", value.get("instances", [])):
                if isinstance(item, dict) and item.get("type") in names:
                    item["type"] = names[item["type"]]
                    changed = True
            for child in value.values():
                changed = convert(child) or changed
        elif isinstance(value, list):
            for child in value:
                changed = convert(child) or changed
        return changed

    for name in ("ScriptConfig.json", "PlanConfig.json", "scripts.yaml", "plans.yaml"):
        path = config_path / name
        if not path.is_file():
            continue
        if is_blank_file(path):
            continue
        document = _utils_io.read_dict_file(path)
        changed = convert(document)
        index = document.get("order", document.get("instances", []))
        entries = document.get("data", document)
        for item in index:
            if item["type"] != "MaaConfig":
                continue
            update = entries[item["uid"]].setdefault("Update", {})
            if "TakeoverMigrationVersion" not in update:
                update["TakeoverMigrationVersion"] = 0
                changed = True
            if "ChannelMigrationVersion" not in update and "Channel" not in update:
                update["ChannelMigrationVersion"] = 0
                changed = True
        if changed:
            backup = config_path / "legacy-plugin" / name
            if not backup.exists():
                _utils_io.atomic_write(backup, path.read_bytes())
            _utils_io.write_file(path, document)


async def migrate_maa_update_channel(config: Any, *, data_path: Path) -> None:
    """旧脚本首次升级沿用原配置通道；持久化后只服从用户的新选择。"""
    if config.Update.ChannelMigrationVersion:
        return
    from app.task.proxy_helpers import (
        CONFIG_BASE_NATIVE,
        CONFIG_BASE_SHARED,
        read_config_base,
    )

    # 此时所需插件已经安装并加载；仅复用正常更新业务的只读识别能力，
    # 不再由插件声明迁移钩子或负责迁移写入。
    software = import_module("maa_adapter.updates.software.service")
    install = config.Info.Path
    root = data_path / str(config.uid)
    directories = []
    for user_id, user in config.UserData.items():
        if not user.Info.Status or user.Info.RemainedDay == 0:
            continue
        base = read_config_base(user, CONFIG_BASE_SHARED)
        if base == CONFIG_BASE_NATIVE:
            if install is not None:
                directories.append(install / "config")
        elif base == CONFIG_BASE_SHARED:
            directories.append(root / "Default" / "ConfigFile")
        else:
            directories.append(root / str(user_id) / "ConfigFile")
    directories.append(root / "Default" / "ConfigFile")
    if install is not None:
        directories.append(install / "config")
    channel = next(
        (
            value
            for directory in directories
            if (value := software.read_config_channel(directory))
        ),
        None,
    )
    if channel is None and install is not None:
        release = software.read_installed_release(install)
        channel = software.detect_channel(release[0]) if release else None
    # 界面只开放正式版与公测版；旧 nightly 归入公测选项，安装仍受不降级守卫保护。
    channel = "beta" if channel in ("beta", "alpha") else "stable"
    await config.update(
        type(config).model_validate(
            {"Update": {"Channel": channel, "ChannelMigrationVersion": 1}}
        ),
        check_visibility=False,
    )


async def migrate_adapter_configs(config: Any) -> None:
    """仅在主程序插件化升级段落中迁移已有托管，按现有标记保持重试幂等。"""
    from app.core import Plugin

    for script in config.ScriptConfig.values():
        decl = Plugin.script_decl(script)
        if decl is None or decl.script_type.__name__ != "MaaConfig":
            continue
        if not script.Update.TakeoverMigrationVersion:
            enabled = bool(
                script.Update.MirrorChyanCDK.strip()
                or config.setting.Update.MirrorChyanCDK.strip()
            )
            values = {"TakeoverMigrationVersion": 1}
            if enabled:
                values["TakeoverEnabled"] = True
            await script.update(type(script).model_validate({"Update": values}))
        await migrate_maa_update_channel(script, data_path=config.data_path)
