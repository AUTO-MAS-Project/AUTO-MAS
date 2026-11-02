"""脚本中文输出不应随 Windows 系统代码页变成乱码。"""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("system_encoding", ["cp1252", "gbk"])
@pytest.mark.parametrize("output_encoding", ["utf-8", "gbk"])
def test_chinese_output_preserves_text(system_encoding, output_encoding):
    text = "正常输出\n停止运行\n正常尾部"
    code = (
        "import locale; "
        f"locale.getpreferredencoding = lambda: {system_encoding!r}; "
        "from app.task.HSR.tools.m7a_runtime import M7ARunner; "
        f"assert M7ARunner._decode_stream_output({text.encode(output_encoding)!r}) == {text!r}"
    )
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, timeout=10
    )


def test_system_ansi_config_is_not_redecoded_as_gbk():
    code = (
        "import locale; "
        "locale.getpreferredencoding = lambda: 'cp1252'; "
        "from app.utils.common.process.runner import decode_bytes; "
        'assert decode_bytes(b\'{"name":"Caf\\xe9Tool"}\') == \'{"name":"CaféTool"}\''
    )
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, timeout=10
    )
