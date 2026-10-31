#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""General 模板导入、分享整理与隐私策略；配置和网络能力由宿主注入。"""

import os
import re
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.config import ConfigEntry
from app.models.config import GeneralConfig
from app.services import ConfigCenterError
from app.utils import IS_WINDOWS, get_logger

logger = get_logger("通用脚本分享")


class GeneralShareStore(Protocol):
    """查询脚本并提交字段更新，不向专项暴露宿主配置中心。"""

    def get_script(self, uid: UUID) -> ConfigEntry | None: ...

    async def update_script(self, uid: UUID, config: GeneralConfig) -> None: ...


class GeneralShareCenter(Protocol):
    """分享业务只消费模板下载与配置上传。"""

    async def download_template(
        self, config_key: str, version_no: int | None
    ) -> Any: ...

    async def upload_config(
        self, display_name: str, description: str, config: dict[str, Any]
    ) -> dict[str, Any]: ...


class GeneralShareService:
    def __init__(
        self, *, scripts: GeneralShareStore, config_center: GeneralShareCenter
    ) -> None:
        self._scripts = scripts
        self._config_center = config_center

    def _get_script(self, script_id: str) -> GeneralConfig:
        script = self._scripts.get_script(UUID(script_id))
        if script is None:
            logger.error(f"{script_id} 不存在")
            raise KeyError(f"脚本 {script_id} 不存在")
        if not isinstance(script, GeneralConfig):
            logger.error(f"{script_id} 不是通用脚本配置")
            raise TypeError(f"脚本 {script_id} 不是通用脚本配置")
        return script

    async def import_script_from_share(
        self, script_id: str, config_key: str, version_no: int | None
    ) -> None:
        """下载模板并更新已提供字段，保留本地用户、Webhook 和历史格式兼容。"""
        logger.info(f"从配置中心加载脚本配置: {script_id} - {config_key}")
        self._get_script(script_id)
        data = await self._config_center.download_template(config_key, version_no)
        if not isinstance(data, dict) or not isinstance(data.get("Script"), dict):
            raise ConfigCenterError("配置文件不是通用脚本配置, 无法导入")

        # 网页端手工上传的模板也可能携带账号数据；这些内容不参与导入。
        data = {
            key: value
            for key, value in data.items()
            if key not in {"SubConfigsInfo", "UserData", "Notify_CustomWebhooks", "ui"}
        }
        config = GeneralConfig.model_validate(GeneralConfig.normalize_payload(data))
        # 只更新 MAS 面板字段，不覆盖原生文件或用户 ConfigFile，归档池保持原职责。
        await self._scripts.update_script(UUID(script_id), config)
        logger.success(f"{script_id} 配置加载成功")

    def build_share_config(
        self, script_id: str, config_name: str
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        """从独立导出整理分享内容，不修改原配置；风险项交由用户确认。"""
        script = self._get_script(script_id)
        config = script.model_dump(context={"audience": "persist"})
        config.pop("UserData", None)
        config.pop("Notify_CustomWebhooks", None)
        config.pop("ui", None)
        config = remove_privacy_info(config, config_name)
        return config, scan_privacy_risks(config)

    async def upload_script_to_share(
        self,
        script_id: str,
        config_name: str,
        description: str,
        acknowledged: bool,
    ) -> None:
        """重新检查当前配置，存在未确认风险时阻止上传。"""
        logger.info(f"上传配置到配置中心: {script_id} - {config_name}")
        config, risks = self.build_share_config(script_id, config_name)
        if risks and not acknowledged:
            logger.warning(f"分享前检查到 {len(risks)} 项待确认内容, 已阻止上传")
            raise ConfigCenterError("配置中仍有可能泄露隐私的内容, 请确认后再分享")
        await self._config_center.upload_config(
            display_name=config_name, description=description, config=config
        )


def remove_privacy_info(config: dict[str, Any], name: str) -> dict[str, Any]:
    """在待分享的独立导出上替换名称和路径，不接触 live 配置。"""
    config["Info"]["Name"] = name
    root_value = config["Info"]["RootPath"]
    root_path = Path(root_value) if root_value else None
    for path in ["ScriptPath", "ConfigPath", "LogPath", "TrackProcessExe"]:
        path_value = config["Script"][path]
        if not path_value:
            continue
        script_path = Path(path_value)
        if root_path is not None and script_path.is_relative_to(root_path):
            config["Script"][path] = str(
                Path(r"C:/脚本根目录") / script_path.relative_to(root_path)
            )
        elif IS_WINDOWS and script_path.is_relative_to(Path(os.environ["APPDATA"])):
            config["Script"][path] = (
                f"%APPDATA%/{script_path.relative_to(Path(os.environ['APPDATA']))}"
            )
    if root_path is not None:
        config["Info"]["RootPath"] = str(Path(r"C:/脚本根目录"))

    # 上面只覆盖脚本自身的路径项；游戏路径、命令行等自由文本同样会带出本机用户名。
    for items in config.values():
        if not isinstance(items, dict):
            continue
        for key, value in items.items():
            if isinstance(value, str) and value:
                items[key] = _mask_home_path(value)
    return config


def _mask_home_path(value: str) -> str:
    """把值里出现的本机用户目录替换成占位符。"""
    home = str(Path.home())
    if not home:
        return value
    masked = value
    for candidate in {home, home.replace("\\", "/")}:
        # 要求用户目录后面是分隔符或行尾，避免误切同名前缀的其他用户目录。
        masked = re.sub(
            rf"{re.escape(candidate)}(?=[\\/]|$)",
            "%USERPROFILE%",
            masked,
            flags=re.IGNORECASE,
        )
    return masked


def scan_privacy_risks(config: dict[str, Any]) -> list[dict[str, str]]:
    """检查脱敏后自由文本中的凭据、用户名和绝对路径，返回待确认风险项。"""
    placeholders = ("C:\\脚本根目录", "C:/脚本根目录", "%APPDATA%", "%USERPROFILE%")
    user_name = Path.home().name
    risks: list[dict[str, str]] = []
    for group, items in config.items():
        if not isinstance(items, dict):
            continue
        for key, value in items.items():
            if not isinstance(value, str) or not value.strip():
                continue
            field = f"{group}.{key}"
            if re.search(
                r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|cookie|session"
                r"|密码|密钥|口令)\s*[=:\s]\s*\S",
                value,
            ):
                risks.append({"field": field, "reason": "疑似包含账号、密码或令牌"})
                continue
            if re.search(r"://[^/\s:@]+:[^/\s@]+@", value):
                risks.append({"field": field, "reason": "链接中带有账号密码"})
                continue
            if len(user_name) > 2 and user_name.lower() in value.lower():
                risks.append({"field": field, "reason": "包含本机用户名"})
                continue
            probe = value
            for placeholder in placeholders:
                probe = probe.replace(placeholder, "")
            # 盘符前不能跟字母，避免把 https:// 等协议头误判为盘符路径。
            if re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", probe) or "\\\\" in probe:
                risks.append({"field": field, "reason": "包含本机绝对路径"})
    return risks
