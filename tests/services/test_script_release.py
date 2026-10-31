from unittest.mock import Mock

import httpx
import pytest

from app.services import script_release as release


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel, expected", [("stable", "v2.0.0"), ("beta", "v2.1.0-beta.2")]
)
async def test_release_selection_preserves_proxy_and_channel(
    monkeypatch, channel, expected
):
    proxy = httpx.Proxy("http://user:secret@127.0.0.1:7890")
    payload = [
        {"tag_name": "v2.0.0", "prerelease": False},
        {"tag_name": "v2.1.0-beta.1", "prerelease": True},
        {"tag_name": "v2.1.0-beta.2", "prerelease": True},
        {"tag_name": "v3.0.0", "draft": True},
        {"tag_name": "v4.0.0.dev1"},
        {"tag_name": "unrecognizable"},
        {"tag_name": None},
        None,
    ]
    urls = []

    def respond(request):
        urls.append(str(request.url))
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient

    def create(**kwargs):
        assert kwargs.pop("proxy") is proxy
        return client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(release.httpx, "AsyncClient", create)
    result = await release.request_github_release(
        "MaaEnd/MaaEnd", channel=channel, proxy=proxy
    )
    assert result["tag_name"] == expected
    assert urls == [
        "https://api.github.com/repos/MaaEnd/MaaEnd/"
        + ("releases/latest" if channel == "stable" else "releases?per_page=100")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repository, channel",
    [
        ("../other", "stable"),
        ("https://example.invalid/repo", "stable"),
        ("owner/repo", "unknown"),
    ],
)
async def test_invalid_source_never_starts_network(monkeypatch, repository, channel):
    client = Mock()
    monkeypatch.setattr(release.httpx, "AsyncClient", client)
    with pytest.raises(ValueError):
        await release.request_github_release(repository, channel=channel)
    client.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"tag_name": "v1.1.0-beta.1", "prerelease": True},
        {"tag_name": "v1.0.0", "draft": True},
        {"message": "not a release"},
        [],
    ],
)
async def test_invalid_stable_release_is_not_accepted(monkeypatch, payload):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        release.httpx,
        "AsyncClient",
        lambda **kwargs: client(
            **kwargs,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload)
            ),
        ),
    )
    with pytest.raises(ValueError):
        await release.request_github_release("owner/repo")
