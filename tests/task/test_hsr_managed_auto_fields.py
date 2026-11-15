"""HSR 托管表单自动跟进：只露出当前任务真的会读的原生设置。"""

from app.task.HSR.tools.m7a_config import m7a_auto_patch_keys
from app.task.HSR.tools.managed_fields import auto_managed_keys

# 三月七 v2026.11.16 样例配置里差分宇宙一节的相关键
_M7A_DIVERGENT_NATIVE = {
    "weekly_divergent_enable": True,
    "weekly_divergent_type": "cycle",
    "divergent_auto_save_enable": True,
    "divergent_station_priority_enable": False,
    "divergent_universe_daily_completed_count": 0,
    "divergent_universe_daily_completed_timestamp": 0,
    "divergent_type": "normal",
    "divergent_team_type": "终结技",
}


def test_m7a_divergent_auto_fields_skip_settings_the_task_ignores():
    """队伍类型只给外置 ASU 路径用，周常差分不读，不进表单也不进可写集合。"""

    auto = auto_managed_keys("M7A", "DivergentUniverse", _M7A_DIVERGENT_NATIVE)

    assert auto == ("divergent_station_priority_enable",)
    patch_keys = m7a_auto_patch_keys(_M7A_DIVERGENT_NATIVE)
    assert "divergent_station_priority_enable" in patch_keys
    assert "divergent_team_type" not in patch_keys
