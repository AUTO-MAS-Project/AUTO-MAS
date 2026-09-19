"""MFW 子进程代理贯通（``runtime_pool/host_environment`` + ``Config.proxy_url``）的纯逻辑回归。

用户在 MAS 里填的 ``Update.ProxyAddress`` 此前从没交给过 uv / pip / worker；现在所有 MFW
子进程环境都经 ``strip_host_python_environment`` 派生，代理只在那一处按线程作用域注入。
本文件覆盖：env 构造（NO_PROXY 合并、空值不动、userinfo 保留）、地址规范化、作用域进出。
"""

from __future__ import annotations

import threading

from app.core.config import normalize_proxy_address
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    apply_proxy_environment,
    current_subprocess_proxy,
    strip_host_python_environment,
    subprocess_proxy_scope,
)

# ---------------------------------------------------------------------------
# apply_proxy_environment
# ---------------------------------------------------------------------------


def test_apply_proxy_sets_three_variables_and_loopback_no_proxy() -> None:
    env = apply_proxy_environment({"PATH": "x"}, "http://127.0.0.1:7890")
    assert env["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert env["ALL_PROXY"] == "http://127.0.0.1:7890"
    # 已证实验：uv 对 127.0.0.1 也走代理，NO_PROXY=localhost 不豁免 127.0.0.1，两条都要
    assert env["NO_PROXY"] == "127.0.0.1,localhost"
    assert env["PATH"] == "x"


def test_apply_proxy_merges_existing_no_proxy_without_duplicates() -> None:
    env = apply_proxy_environment(
        {"NO_PROXY": "localhost, .internal.example ,127.0.0.1"},
        "http://proxy:8080",
    )
    assert env["NO_PROXY"] == "localhost,.internal.example,127.0.0.1"


def test_apply_proxy_merges_lowercase_no_proxy_and_keeps_it_in_sync() -> None:
    env = apply_proxy_environment(
        {"no_proxy": "corp.local", "http_proxy": "http://old:1"},
        "http://proxy:8080",
    )
    assert env["NO_PROXY"] == "corp.local,127.0.0.1,localhost"
    assert env["no_proxy"] == env["NO_PROXY"]
    # 已存在的小写变量改成一致的值，不留两份互相打架
    assert env["http_proxy"] == "http://proxy:8080"
    assert env["HTTP_PROXY"] == "http://proxy:8080"
    assert "https_proxy" not in env


def test_apply_proxy_with_empty_value_leaves_environment_untouched() -> None:
    source = {"HTTP_PROXY": "http://user-system:3128", "NO_PROXY": "a"}
    for empty in (None, "", "   "):
        env = apply_proxy_environment(source, empty)
        assert env == source
        assert env is not source


def test_apply_proxy_preserves_userinfo() -> None:
    env = apply_proxy_environment({}, "http://alice:s3cr%40t@proxy.example:3128")
    assert env["HTTPS_PROXY"] == "http://alice:s3cr%40t@proxy.example:3128"


# ---------------------------------------------------------------------------
# normalize_proxy_address
# ---------------------------------------------------------------------------


def test_normalize_proxy_address_adds_http_scheme_and_strips() -> None:
    assert normalize_proxy_address("  127.0.0.1:7890 ") == "http://127.0.0.1:7890"


def test_normalize_proxy_address_keeps_explicit_schemes() -> None:
    for value in (
        "http://p:1",
        "https://p:1",
        "socks5://p:1",
        "socks5h://p:1",
        "SOCKS5://p:1",
    ):
        assert normalize_proxy_address(value) == value


def test_normalize_proxy_address_keeps_userinfo() -> None:
    assert normalize_proxy_address("user:pw@proxy:3128") == "http://user:pw@proxy:3128"
    assert (
        normalize_proxy_address("http://user:pw@proxy:3128")
        == "http://user:pw@proxy:3128"
    )


def test_normalize_proxy_address_empty_is_none() -> None:
    assert normalize_proxy_address(None) is None
    assert normalize_proxy_address("") is None
    assert normalize_proxy_address("   ") is None


# ---------------------------------------------------------------------------
# 线程本地作用域 + strip_host_python_environment 末尾注入
# ---------------------------------------------------------------------------


def test_scope_enter_exit_and_thread_locality() -> None:
    assert current_subprocess_proxy() is None
    with subprocess_proxy_scope("http://proxy:8080"):
        assert current_subprocess_proxy() == "http://proxy:8080"
        # 嵌套：内层 None 覆盖，退出后恢复外层
        with subprocess_proxy_scope(None):
            assert current_subprocess_proxy() is None
        assert current_subprocess_proxy() == "http://proxy:8080"

        seen: list[str | None] = []
        worker = threading.Thread(
            target=lambda: seen.append(current_subprocess_proxy())
        )
        worker.start()
        worker.join()
        # 别的线程看不到本线程的作用域
        assert seen == [None]
    assert current_subprocess_proxy() is None


def test_scope_treats_blank_as_no_proxy() -> None:
    with subprocess_proxy_scope("   "):
        assert current_subprocess_proxy() is None


def test_strip_host_environment_injects_proxy_only_inside_scope(monkeypatch) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", "p")

    outside = strip_host_python_environment()
    assert "HTTP_PROXY" not in outside

    with subprocess_proxy_scope("http://proxy:8080"):
        inside = strip_host_python_environment()
    assert inside["HTTP_PROXY"] == "http://proxy:8080"
    assert inside["HTTPS_PROXY"] == "http://proxy:8080"
    assert inside["ALL_PROXY"] == "http://proxy:8080"
    assert inside["NO_PROXY"] == "127.0.0.1,localhost"
    # 作用域退出后不再注入
    after = strip_host_python_environment()
    assert "HTTP_PROXY" not in after


def test_strip_host_environment_applies_scope_to_explicit_mapping() -> None:
    with subprocess_proxy_scope("http://proxy:8080"):
        env = strip_host_python_environment({"PYTHONHOME": "x", "KEEP": "1"})
    assert "PYTHONHOME" not in env
    assert env["KEEP"] == "1"
    assert env["HTTPS_PROXY"] == "http://proxy:8080"
