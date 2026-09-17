"""SRA 2.22.0 具名奖励开关（rewards.<name>）下的临时配置构造回归

SRA 2.22.0 把 receiveRewards 的奖励项从数组 ``rewards[0..6]`` 改成平铺的具名键
``rewards.trailblazeProfile`` … ``rewards.redeemCode``，读取时具名键优先、数组只作
旧版兼容。MAS 此前把所有 ``rewards.*`` 都当数组下标，遇到具名键在队列构建期就
``int("trailblazeProfile")`` 炸掉整个用户；兑换码闸门也只落在数组第 6 位。
"""

import json
from pathlib import Path
from unittest import mock

import pytest

import app.core  # noqa: F401  # 初始化宿主配置
from app.task.HSR.task_mapping import HSR_TASK_MODULES
from app.task.HSR.tools import sra_runtime
from app.task.HSR.tools.sra_runtime import build_sra_module_config

RECEIVE_REWARDS = next(m for m in HSR_TASK_MODULES if m.key == "ReceiveRewards")

# 照抄 SRA 2.22.0 SRAFrontend/Models/TasksConfig.cs 里 ReceiveRewardsConfig 的
# JsonPropertyName 顺序；旧版数组下标按这个顺序对应。
NAMED_REWARD_KEYS = (
    "rewards.trailblazeProfile",
    "rewards.assignments",
    "rewards.mail",
    "rewards.dailyTraining",
    "rewards.namelessHonor",
    "rewards.giftOfOdyssey",
    "rewards.redeemCode",
)


class _Config:
    def __init__(self, data: dict[tuple[str, str], object] | None = None):
        self._data = data or {}

    def get(self, section: str, key: str):
        return self._data.get((section, key))


def _sra_profile(receive_rewards: dict) -> dict:
    return {
        "name": "Default",
        "trailblazePower": {"tasklist": [], "enabled": True},
        "receiveRewards": {"enabled": True, "redeemCodes": "", **receive_rewards},
        "cosmicStrife": {"enabled": False},
    }


@pytest.fixture
def profile(tmp_path: Path):
    path = tmp_path / "Default.json"

    def use(receive_rewards: dict) -> Path:
        path.write_text(
            json.dumps(_sra_profile(receive_rewards), ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    with mock.patch.object(
        sra_runtime, "resolve_sra_profile", lambda cfg: ("Default", path)
    ):
        yield use


def test_named_reward_keys_are_mirrored_into_temp_config(profile) -> None:
    """2.22.0 具名开关原样写进临时配置，且不再因 int('trailblazeProfile') 中止。"""

    named = {key: True for key in NAMED_REWARD_KEYS}
    named["rewards.mail"] = False
    profile(named)

    config = build_sra_module_config(RECEIVE_REWARDS, _Config(), _Config())

    section = config["receiveRewards"]
    assert section["enabled"] is True
    assert {key: section[key] for key in NAMED_REWARD_KEYS} == named


def test_legacy_reward_list_still_maps_by_index(profile) -> None:
    """旧版数组形态的 profile 行为不变。"""

    profile({"rewards": [True, False, True, True, True, True, True]})

    config = build_sra_module_config(RECEIVE_REWARDS, _Config(), _Config())

    section = config["receiveRewards"]
    assert section["rewards"] == [True, False, True, True, True, True, True]
    assert not any(key in section for key in NAMED_REWARD_KEYS)


def test_redeem_code_gate_covers_named_key(profile) -> None:
    """兑换码「仅变化时领取」闸门在具名开关上也要生效，否则 SRA 会按具名键照领。"""

    profile({key: True for key in NAMED_REWARD_KEYS})

    config = build_sra_module_config(
        RECEIVE_REWARDS, _Config(), _Config(), redeem_codes_enabled=False
    )

    section = config["receiveRewards"]
    assert section["rewards.redeemCode"] is False
    assert section["rewards"][6] is False


def test_user_override_applies_to_named_key(profile) -> None:
    """用户在 MAS 托管表单里关掉某项具名开关，覆盖值要落到同名键上。"""

    profile({key: True for key in NAMED_REWARD_KEYS})
    user = _Config(
        {("Managed", "Options"): {"SRA": {"ReceiveRewards": {"rewards.mail": False}}}}
    )

    config = build_sra_module_config(RECEIVE_REWARDS, _Config(), user)

    assert config["receiveRewards"]["rewards.mail"] is False
    assert config["receiveRewards"]["rewards.assignments"] is True
