"""开机自启任务的启动参数与启动诊断文案。

计划任务的动作不是直接指 AUTO-MAS.exe，而是 powershell 引导脚本：脚本走 UAC
提权拉起 app（不提权的话令牌带 TokenMandatoryPolicy=3，MuMu 6.8.8 会因此自降
权限、拉不起 MuMuNxMain），再等 app 退出。这里锁住三条用户可观察的约束：

1. 安装路径原样进不了命令行——路径里有撇号或 & < > 都不能把命令截断、注入，
   也不能让 schtasks 的 XML 解析失败，所以脚本编码成 base64 下发；
2. 引导脚本必须和 app 同生命周期，否则任务动作秒退，
   MultipleInstancesPolicy=IgnoreNew 挡不住下一次触发，会拉起第二个实例
   抢同一个监听端口；
3. 启动失败时附带的 MuMu 诊断只透传上游字段名，不翻译成我们自己的状态词。

纯字符串与 base64 运算，不依赖 Windows API，因此全平台都跑。
"""

import base64
import re
from pathlib import Path

import pytest

from app.services.platform.windows.startup import (
    WindowsStartupManager,
    build_launch_arguments,
)

_PREFIX = "-NoProfile -WindowStyle Hidden -EncodedCommand "

_QUOTE = chr(39)


def _decode_arguments(arguments: str) -> str:
    """把启动参数里的 base64 还原成 powershell 脚本，顺带确认外壳没夹带别的东西。"""
    assert arguments.startswith(_PREFIX)
    payload = arguments[len(_PREFIX) :]
    assert re.fullmatch(r"[A-Za-z0-9+/=]+", payload), payload
    return base64.b64decode(payload).decode("utf-16-le")


def _unwrap_path(script: str) -> str:
    """取出 -FilePath 后面那段 PowerShell 单引号字符串的原文。"""
    start = script.index("-FilePath ") + len("-FilePath ")
    end = script.index(" -ArgumentList")
    return script[start:end].strip(_QUOTE)


def test_launch_arguments_handles_apostrophe_in_install_path() -> None:
    """安装路径含撇号时，脚本仍能表达出这个路径，而不是被提前闭合。"""
    exe = Path(r"D:\O'Brien\AUTO-MAS\AUTO-MAS.exe")

    script = _decode_arguments(build_launch_arguments(exe))

    # PowerShell 单引号串里撇号要成对写，落在脚本里就是两个撇号。
    assert _unwrap_path(script) == r"D:\O''Brien\AUTO-MAS\AUTO-MAS.exe"
    assert "--auto-start" in script


def test_launch_arguments_cannot_be_broken_by_shell_metacharacters() -> None:
    """路径里的 & < > 只出现在解码后的脚本里，命令行与 schtasks XML 看不到它们。"""
    exe = Path(r"D:\a&b\<c>\AUTO-MAS.exe")

    arguments = build_launch_arguments(exe)

    assert "<" not in arguments and ">" not in arguments and "&" not in arguments
    assert _unwrap_path(_decode_arguments(arguments)) == r"D:\a&b\<c>\AUTO-MAS.exe"


def test_launch_script_waits_for_automas_to_exit() -> None:
    """引导脚本要等 app 退出，任务动作才不会被 Start-Process 立刻结束。"""
    script = _decode_arguments(
        build_launch_arguments(Path(r"D:\AUTO-MAS\AUTO-MAS.exe"))
    )

    assert "-Verb RunAs" in script
    assert "-PassThru" in script
    assert "WaitForExit" in script


class _Result:
    returncode = 0
    stdout = ""
    stderr = ""


async def _create_task_xml(monkeypatch: pytest.MonkeyPatch) -> str:
    """跑一次 _create_task，把写进临时文件、交给 schtasks 的 XML 原文捞回来。"""
    from app.services.platform.windows import startup

    captured: list[str] = []

    async def fake_run_process(*args, **kwargs):
        argv = list(args)
        index = argv.index("/xml") + 1
        captured.append(Path(argv[index]).read_text(encoding="utf-16"))
        return _Result()

    monkeypatch.setattr(
        startup._utils_process_runner.ProcessRunner, "run_process", fake_run_process
    )
    await WindowsStartupManager()._create_task()
    assert len(captured) == 1
    return captured[0]


@pytest.mark.asyncio
async def test_task_xml_ships_encoded_powershell_and_keeps_task_unprivileged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """注册出来的任务仍是不提权的，提权只发生在登录后由引导脚本触发的 UAC。"""
    xml = await _create_task_xml(monkeypatch)

    assert "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert "<Command>powershell.exe</Command>" in xml
    arguments = xml.split("<Arguments>", 1)[1].split("</Arguments>", 1)[0]
    assert "WaitForExit" in _decode_arguments(arguments)


def test_launch_diagnosis_passes_upstream_fields_through() -> None:
    """诊断后缀保留 MuMu 的字段名，只跳过空值与 0。"""
    from app.utils.common.emulator2.mumu6 import format_launch_diagnosis

    text = format_launch_diagnosis(
        {
            "launch_err_code": 5,
            "launch_err_msg": "mainnx connect failed",
            "error_code": 0,
            "player_state": "",
            "unrelated": 7,
        }
    )

    assert text == "；MuMu 诊断: launch_err_code=5, launch_err_msg=mainnx connect failed"


def test_launch_diagnosis_is_empty_when_upstream_says_nothing() -> None:
    """没有诊断时后缀为空串，报错文案与之前完全一样。"""
    from app.utils.common.emulator2.mumu6 import format_launch_diagnosis

    assert format_launch_diagnosis({}) == ""
