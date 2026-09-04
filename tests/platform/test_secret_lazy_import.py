"""`app.utils.platform.secret` 在没有 pywin32 的环境里也必须能被 import。

MaaFW 内置 runner worker 跑在运行池的隔离 venv 中，那里没有 pywin32；worker 一旦
import 到本仓的 ``app.utils``（logger -> security -> platform.secret），顶层的
``import win32crypt`` 就会让它在启动阶段直接崩溃。``win32crypt`` 只能在真正加解密
时再 import。
"""

from __future__ import annotations

import importlib
import sys

import pytest

_SECRET_MODULES = (
    "app.utils.platform.secret",
    "app.utils.platform.windows.secret",
    "app.utils.platform.common.secret",
)


@pytest.fixture
def _without_win32crypt(monkeypatch: pytest.MonkeyPatch):
    # sys.modules 里置 None 会让 ``import win32crypt`` 抛 ModuleNotFoundError，
    # 与池环境「根本没装 pywin32」等价；同时把已加载的 secret 模块清掉，
    # 强制走一遍真正的模块顶层 import。monkeypatch 会在用例结束后恢复原状。
    monkeypatch.setitem(sys.modules, "win32crypt", None)
    for name in _SECRET_MODULES:
        if name in sys.modules:
            monkeypatch.delitem(sys.modules, name)
    yield


@pytest.mark.usefixtures("_without_win32crypt")
def test_secret_module_imports_without_pywin32() -> None:
    module = importlib.import_module("app.utils.platform.secret")

    assert callable(module.dpapi_encrypt)
    assert callable(module.dpapi_decrypt)
    # 空串短路不需要 DPAPI，任何环境下都应直接返回。
    assert module.dpapi_encrypt("") == ""
    assert module.dpapi_decrypt("") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows 走 DPAPI 实现")
@pytest.mark.usefixtures("_without_win32crypt")
def test_windows_secret_defers_win32crypt_to_call_time() -> None:
    module = importlib.import_module("app.utils.platform.windows.secret")

    with pytest.raises(ModuleNotFoundError):
        module.dpapi_encrypt("plain-text")
    with pytest.raises(ModuleNotFoundError):
        module.dpapi_decrypt("not-really-encrypted")
