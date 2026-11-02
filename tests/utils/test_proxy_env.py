"""Per-process proxy settings preserve authentication without changing the host."""

import os
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from app.utils.common.proxy_env import proxy_environment


def test_no_explicit_proxy_keeps_default_environment():
    assert proxy_environment(None) is None


@pytest.mark.parametrize("authenticated", [False, True])
def test_explicit_proxy_overrides_inherited_values(monkeypatch, authenticated):
    monkeypatch.setenv("HTTP_PROXY", "http://old.invalid:1")
    monkeypatch.setenv("https_proxy", "http://old.invalid:2")
    monkeypatch.setenv("ALL_PROXY", "socks5://old.invalid:3")
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("MAS_TEST_INHERITED", "kept")
    original = dict(os.environ)
    auth = ("name:@", "password:/@%") if authenticated else None
    proxy = httpx.Proxy("http://[::1]:7890", auth=auth)
    environment = proxy_environment(proxy)
    assert environment is not None
    assert os.environ == original
    assert environment["MAS_TEST_INHERITED"] == "kept"
    assert environment["http_proxy"] == environment["https_proxy"]
    assert environment["no_proxy"] == ""
    assert not {"HTTP_PROXY", "ALL_PROXY", "NO_PROXY"} & environment.keys()
    url = urlsplit(environment["https_proxy"])
    assert url.hostname == "::1" and url.port == 7890
    if auth:
        assert unquote(url.username or "") == auth[0]
        assert unquote(url.password or "") == auth[1]
    else:
        assert url.username is None
