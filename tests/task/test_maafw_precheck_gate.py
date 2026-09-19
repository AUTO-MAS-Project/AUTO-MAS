"""运行前更新的预检备忘闸门：轻探判定与备忘生命周期。

上次预检失败的目标版本，这次运行前先并发探一下 PyPI simple 页与 GitHub 的
tag 源码包（只看有没有），拿得到才重新更新。HTTP 全部用 ``httpx.MockTransport``
替身：ustc 会 301 所以要跟跳转；codeload 只有 200 算可得；回环中继不探；
离线时整个跳过。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from app.task.MaaFW.tools.core.automas_maafw_project_update.precheck_memo import (
    KIND_BINDING_UNAVAILABLE,
    KIND_OTHER,
    read_runtime_precheck,
    write_runtime_precheck,
)
from app.task.MaaFW.tools.embedded.precheck_gate import (
    MAAFW_CODELOAD_URL,
    build_precheck_gate,
    exact_maafw_version,
    maafw_git_tag_for,
    probe_binding_available,
)

VERSION = "5.14.0b1"
TAG = "v5.14.0-beta.1"
SIMPLE_PAGE_WITHOUT = (
    "<!DOCTYPE html><html><body>"
    '<a href="https://files.pythonhosted.org/.../maafw-5.13.1-py3-none-any.whl'
    '#sha256=abc">maafw-5.13.1-py3-none-any.whl</a><br/>'
    "</body></html>"
)
SIMPLE_PAGE_WITH = SIMPLE_PAGE_WITHOUT.replace(
    "</body>",
    '<a href="https://files.pythonhosted.org/.../MaaFW-5.14.0b1-py3-none-any.whl'
    '#sha256=def">MaaFW-5.14.0b1-py3-none-any.whl</a><br/></body>',
)


# ---------------------------------------------------------------------------
# PEP 440 → tag、requirement → 版本
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("5.14.0b1", "v5.14.0-beta.1"),
        ("5.14.0-beta.1", "v5.14.0-beta.1"),
        ("5.13.1", "v5.13.1"),
        ("5.14.0a2", "v5.14.0-alpha.2"),
        ("5.14.0rc1", "v5.14.0-rc.1"),
        ("5.13.1.post6", None),
        ("5.13.1.dev3", None),
        ("5.13.1+ci.123", None),
        ("not-a-version", None),
    ],
)
def test_maafw_git_tag_for(version: str, tag: str | None) -> None:
    assert maafw_git_tag_for(version) == tag


@pytest.mark.parametrize(
    ("requirement", "version"),
    [
        ("maafw==5.14.0b1", "5.14.0b1"),
        ("MaaFw==5.14.0-beta.1", "5.14.0b1"),
        ("maafw", None),
        ("maafw>=5.13", None),
        ("maafw==5.13,!=5.13.1", None),
        ("numpy==2.0", None),
        ("", None),
    ],
)
def test_exact_maafw_version(requirement: str, version: str | None) -> None:
    assert exact_maafw_version(requirement) == version


# ---------------------------------------------------------------------------
# 轻探
# ---------------------------------------------------------------------------


class _Fake:
    """按 URL 前缀应答的 MockTransport，记录探过哪些地址。"""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for prefix, answer in self.routes.items():
            if url.startswith(prefix):
                if callable(answer):
                    return answer(request)
                return answer
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def hit(self, prefix: str) -> bool:
        return any(str(r.url).startswith(prefix) for r in self.requests)


CODELOAD = MAAFW_CODELOAD_URL.format(tag=TAG)


@pytest.mark.asyncio
async def test_index_page_listing_the_wheel_means_available() -> None:
    fake = _Fake(
        {
            "https://pypi.org/simple/maafw/": httpx.Response(
                200, text=SIMPLE_PAGE_WITH
            ),
            CODELOAD: httpx.Response(404),
        }
    )

    assert await probe_binding_available(
        VERSION, index_candidates=None, transport=fake.transport
    )
    assert fake.hit("https://pypi.org/simple/maafw/"), "未受监督时探 pypi.org"


@pytest.mark.asyncio
async def test_neither_index_nor_codeload_means_unavailable() -> None:
    fake = _Fake(
        {
            "https://pypi.org/simple/maafw/": httpx.Response(
                200, text=SIMPLE_PAGE_WITHOUT
            ),
            CODELOAD: httpx.Response(404),
        }
    )

    assert not await probe_binding_available(VERSION, transport=fake.transport)
    assert fake.hit(CODELOAD), "GitHub 也要探"


@pytest.mark.asyncio
async def test_codeload_200_alone_means_available() -> None:
    fake = _Fake(
        {
            "https://pypi.org/simple/maafw/": httpx.Response(
                200, text=SIMPLE_PAGE_WITHOUT
            ),
            CODELOAD: httpx.Response(200),
        }
    )

    assert await probe_binding_available(VERSION, transport=fake.transport)
    assert fake.requests[-1].method == "HEAD" or any(
        r.method == "HEAD" for r in fake.requests
    ), "codeload 只 HEAD，不下载 1.2 MB 源码包"


@pytest.mark.asyncio
async def test_ustc_redirect_is_followed() -> None:
    fake = _Fake(
        {
            "https://mirrors.ustc.edu.cn/pypi/simple/maafw/": httpx.Response(
                301,
                headers={"Location": "https://mirrors.ustc.edu.cn/pypi/simple/maafw"},
            ),
            "https://mirrors.ustc.edu.cn/pypi/simple/maafw": httpx.Response(
                200, text=SIMPLE_PAGE_WITH
            ),
            CODELOAD: httpx.Response(404),
        }
    )

    assert await probe_binding_available(
        VERSION,
        index_candidates=["https://mirrors.ustc.edu.cn/pypi/simple/"],
        transport=fake.transport,
    )
    assert any(str(r.url).endswith("/simple/maafw") for r in fake.requests), (
        "301 之后要跟到去掉尾斜杠的那个地址"
    )


@pytest.mark.asyncio
async def test_loopback_relay_is_skipped_but_mirrors_are_probed() -> None:
    fake = _Fake(
        {
            "https://mirrors.aliyun.com/pypi/simple/maafw/": httpx.Response(
                200, text=SIMPLE_PAGE_WITHOUT
            ),
            CODELOAD: httpx.Response(404),
        }
    )

    assert not await probe_binding_available(
        VERSION,
        index_candidates=[
            "http://127.0.0.1:41234/simple/",
            "http://localhost:41234/simple",
            "https://mirrors.aliyun.com/pypi/simple/",
        ],
        transport=fake.transport,
    )
    assert not fake.hit("http://127.0.0.1")
    assert not fake.hit("http://localhost")
    assert fake.hit("https://mirrors.aliyun.com/pypi/simple/maafw/")


@pytest.mark.asyncio
async def test_offline_skips_probing_entirely() -> None:
    fake = _Fake({})

    assert not await probe_binding_available(
        VERSION, offline=True, transport=fake.transport
    )
    assert fake.requests == []


@pytest.mark.asyncio
async def test_probe_errors_count_as_unavailable() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    fake = _Fake({"https://pypi.org/simple/maafw/": boom, CODELOAD: boom})

    assert not await probe_binding_available(VERSION, transport=fake.transport)


@pytest.mark.asyncio
async def test_nightly_version_only_probes_index() -> None:
    fake = _Fake({"https://pypi.org/simple/maafw/": httpx.Response(200, text="")})

    assert not await probe_binding_available("5.13.1.post6", transport=fake.transport)
    assert not fake.hit("https://codeload.github.com/"), "映射不出 tag 就不探 GitHub"


# ---------------------------------------------------------------------------
# 闸门：备忘的生命周期
# ---------------------------------------------------------------------------


class _Probe:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.calls: list[str] = []

    async def __call__(self, version: str) -> bool:
        self.calls.append(version)
        return self.result


def _memo(kind: str = KIND_BINDING_UNAVAILABLE, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "targetVersion": "v2.29.0",
        "requirement": "maafw==5.14.0b1",
        "kind": kind,
        "reason": "there is no version of maafw==5.14.0b1",
    }
    payload.update(extra)
    return payload


@pytest.fixture
def harness(tmp_path: Path) -> dict[str, Any]:
    operations = tmp_path / "data" / "maafw_update_operations"
    project = tmp_path / "maaend"
    project.mkdir()
    logs: list[str] = []

    def build(probe: _Probe | None) -> Any:
        return build_precheck_gate(
            project,
            project_name="MaaEnd",
            send_log=logs.append,
            operation_root=operations,
            probe=probe,
        )

    def memo() -> dict[str, Any] | None:
        return read_runtime_precheck(project, operation_root=operations)

    def write(payload: dict[str, Any]) -> None:
        write_runtime_precheck(project, payload, operation_root=operations)

    return {"build": build, "memo": memo, "write": write, "logs": logs}


@pytest.mark.asyncio
async def test_no_memo_passes_without_probing(harness: dict[str, Any]) -> None:
    probe = _Probe(False)

    assert await harness["build"](probe)("v2.29.0") is None
    assert probe.calls == []


@pytest.mark.asyncio
async def test_memo_for_another_version_is_dropped(harness: dict[str, Any]) -> None:
    harness["write"](_memo(targetVersion="v2.29.0"))
    probe = _Probe(False)

    assert await harness["build"](probe)("v2.30.0") is None
    assert harness["memo"]() is None, "目标版本变了，备忘作废"
    assert probe.calls == []


@pytest.mark.asyncio
async def test_other_kind_is_not_probed_and_counts(harness: dict[str, Any]) -> None:
    harness["write"](_memo(KIND_OTHER, reason="[WinError 112] 磁盘空间不足。"))
    probe = _Probe(True)

    reason = await harness["build"](probe)("v2.29.0")

    assert reason is not None
    assert "v2.29.0" in reason and "磁盘空间不足" in reason
    assert "第 2 次" in reason and "手动更新可强制重试" in reason
    assert probe.calls == [], "other 不轻探"
    memo = harness["memo"]()
    assert memo is not None and memo["attempts"] == 2


@pytest.mark.asyncio
async def test_available_again_clears_memo_and_passes(harness: dict[str, Any]) -> None:
    harness["write"](_memo())
    probe = _Probe(True)

    assert await harness["build"](probe)("v2.29.0") is None
    assert probe.calls == ["5.14.0b1"]
    assert harness["memo"]() is None
    assert any("现已可得" in line for line in harness["logs"])


@pytest.mark.asyncio
async def test_still_unavailable_counts_and_skips(harness: dict[str, Any]) -> None:
    harness["write"](_memo())
    probe = _Probe(False)
    gate = harness["build"](probe)

    first = await gate("v2.29.0")
    second = await gate("v2.29.0")

    assert first == (
        "MaaEnd v2.29.0 需要 maafw 5.14.0b1，PyPI/GitHub 仍不可得，本次不升级（第 2 次）"
    )
    assert second is not None and "第 3 次" in second
    assert probe.calls == ["5.14.0b1", "5.14.0b1"]
    memo = harness["memo"]()
    assert memo is not None and memo["attempts"] == 3
    assert memo["kind"] == KIND_BINDING_UNAVAILABLE, "写回不改 kind"


@pytest.mark.asyncio
async def test_unpinned_requirement_cannot_be_probed(harness: dict[str, Any]) -> None:
    harness["write"](_memo(requirement="maafw"))
    probe = _Probe(True)

    reason = await harness["build"](probe)("v2.29.0")

    assert reason is not None and "需要 maafw，" in reason
    assert probe.calls == [], "没有精确版本号，探不了"


@pytest.mark.asyncio
async def test_probe_exception_is_treated_as_unavailable(
    harness: dict[str, Any],
) -> None:
    harness["write"](_memo())

    async def broken(_version: str) -> bool:
        raise RuntimeError("dns down")

    reason = await harness["build"](broken)("v2.29.0")

    assert reason is not None and "仍不可得" in reason
    memo = harness["memo"]()
    assert memo is not None and memo["attempts"] == 2


@pytest.mark.asyncio
async def test_gate_end_to_end_with_http_transport(harness: dict[str, Any]) -> None:
    """不换替身、走真正的轻探（MockTransport）：simple 页有 wheel 就放行。"""

    harness["write"](_memo())
    fake = _Fake(
        {
            "https://pypi.org/simple/maafw/": httpx.Response(
                200, text=SIMPLE_PAGE_WITH
            ),
            CODELOAD: httpx.Response(404),
        }
    )

    async def probe(version: str) -> bool:
        return await probe_binding_available(
            version, index_candidates=None, transport=fake.transport
        )

    assert await harness["build"](probe)("v2.29.0") is None
    assert harness["memo"]() is None
