import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Config
from app.models.config import (
    GeneralConfig,
    GeneralUserConfig,
    MaaConfig,
    MaaUserConfig,
    OkwwConfig,
    OkwwUserConfig,
    ZzzOdConfig,
    ZzzOdUserConfig,
)


class _UserConfigStub:
    """模拟专项用户配置对象的二级 get 访问。"""

    def __init__(self, mode: str) -> None:
        self._mode = mode

    def get(self, group: str, key: str) -> str:
        assert (group, key) == ("Info", "Mode")
        return self._mode


class _UserData:
    """记录添加用户配置时收到的类，模拟专项用户仓库。"""

    def __init__(self) -> None:
        self.added_cls = None
        self.added_uid: uuid.UUID | None = None
        self.removed: list[uuid.UUID] = []

    async def add(self, cls):
        self.added_cls = cls
        self.added_uid = uuid.uuid4()
        return self.added_uid, _UserConfigStub(mode="脚本")

    async def remove(self, uid) -> None:
        self.removed.append(uid)


def test_add_user_dispatches_matching_user_config_class() -> None:
    """按脚本配置实例查 USER_CONFIG_BOOK：各域拿到自己的用户配置类。"""

    for script_config, expected_cls in [
        (MaaConfig(), MaaUserConfig),
        (GeneralConfig(), GeneralUserConfig),
        (ZzzOdConfig(), ZzzOdUserConfig),
    ]:
        user_data = _UserData()
        script_config.UserData = user_data
        script_id = uuid.uuid4()

        with patch.object(Config, "ScriptConfig", {script_id: script_config}):
            uid, _ = asyncio.run(Config.add_user(str(script_id)))

        assert user_data.added_cls is expected_cls
        assert uid == user_data.added_uid


def test_add_user_rejects_unregistered_script_config() -> None:
    """缺失注册的失败模式：明确 TypeError，不落任何默认用户配置。"""

    class _UnknownConfig:
        pass

    script_id = uuid.uuid4()
    with (
        patch.object(Config, "ScriptConfig", {script_id: _UnknownConfig()}),
        pytest.raises(TypeError, match=r"不支持的脚本配置类型"),
    ):
        asyncio.run(Config.add_user(str(script_id)))


def test_add_user_okww_initializes_directory_or_rolls_back() -> None:
    """OK-WW 添加用户后初始化 MAS 目录；初始化失败时回滚新用户。"""

    script_config = OkwwConfig()
    user_data = _UserData()
    script_config.UserData = user_data
    script_id = uuid.uuid4()
    ensure = AsyncMock(side_effect=RuntimeError("目录初始化失败"))

    with (
        patch.object(Config, "ScriptConfig", {script_id: script_config}),
        patch.object(Config, "ensure_okww_user_config", ensure),
        pytest.raises(RuntimeError, match=r"目录初始化失败"),
    ):
        asyncio.run(Config.add_user(str(script_id)))

    assert user_data.added_cls is OkwwUserConfig
    ensure.assert_awaited_once()
    assert ensure.await_args.kwargs["user_id"] == str(user_data.added_uid)
    assert ensure.await_args.kwargs["mode"] == "脚本"
    assert user_data.removed == [user_data.added_uid]
