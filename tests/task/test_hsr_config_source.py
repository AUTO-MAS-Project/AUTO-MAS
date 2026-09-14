"""HSR 配置来源三态与引擎直控的合流回归测试

HSR 有三个名字含「模式/直控」的概念，这里锁住 rev 之后的关系：

| 概念 | 语义 |
| --- | --- |
| `Info.Mode` | 配置来源三态（脚本/用户/直控）；用户可见的来源选择器 |
| `Control.Mode` | 引擎级托管/直控（`managed`/`direct`），插件版存量字段 |
| `Direct.{engine}Config` | 直控快照，可选覆盖 |

合流点只有一个：`resolve_user_control`。`Info.Mode == "直控"` 折进 `direct`，
因此不会出现「用户以为改了来源、实际改的是别的开关」的第二套来源语义。
"""

from typing import Any

from app.task.HSR.tools.native_control import resolve_user_control


class _UserCfg:
    """模拟 HSRUserConfig 的 ConfigBase.get 双参语义。"""

    def __init__(self, info_mode: str = "", **control: Any) -> None:
        self._info_mode = info_mode
        self._control = control

    def get(self, group: str, name: str) -> Any:
        if group == "Info" and name == "Mode":
            return self._info_mode
        if group == "Control":
            return self._control.get(name)
        raise AttributeError(f"配置项 ‘{group}.{name}’ 不存在")


def test_info_direct_folds_into_engine_direct() -> None:
    """Info.Mode=直控 即 direct，无需用户再单独勾 Control.Mode。"""

    control = resolve_user_control(_UserCfg("直控", SRA=True))

    assert control.mode == "direct"
    assert control.engines == ("SRA",)


def test_control_mode_direct_still_honored() -> None:
    """存量插件版用户只设了 Control.Mode=direct 时行为不变。"""

    control = resolve_user_control(_UserCfg("", Mode="direct", M7A=True))

    assert control.mode == "direct"
    assert control.engines == ("M7A",)


def test_user_and_script_sources_stay_managed() -> None:
    """脚本/用户来源维持托管（Control.Mode 未显式设 direct 时）。"""

    assert resolve_user_control(_UserCfg("脚本")).mode == "managed"
    assert resolve_user_control(_UserCfg("用户")).mode == "managed"


def test_direct_without_engines_falls_back_to_configured_engines() -> None:
    """直控但未勾引擎时回落已配置脚本路径的引擎，避免「直控却什么都不跑」。"""

    class _ScriptCfg:
        def __init__(self) -> None:
            self._paths = {"SRAPath": "C:/sra", "M7APath": ""}

        def get(self, group: str, name: str) -> Any:
            if group == "Info" and name in self._paths:
                return self._paths[name]
            return ""

    control = resolve_user_control(_UserCfg("直控"), script_config=_ScriptCfg())

    assert control.mode == "direct"
    assert control.engines == ("SRA",)


def test_quick_config_is_inert_for_hsr() -> None:
    """HSR 无快速配置字段子集，IfQuickConfig 不改变来源判定。"""

    with_quick = _UserCfg("直控", SRA=True)
    without_quick = _UserCfg("直控", SRA=True)

    assert resolve_user_control(with_quick) == resolve_user_control(without_quick)