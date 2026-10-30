import pytest

from app.models.taskboard import TaskboardArchivedActivity, TaskboardVersionStoryUpdate


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://i0.hdslb.com/a.jpg", "https://i0.hdslb.com/a.jpg"),
        ("https://example.com/a.png", "https://example.com/a.png"),
        ("http://example.com/a.png", ""),
        ("https://127.0.0.1/a.png", ""),
        ("https://localhost/a.png", ""),
        ("https://foo.localhost/a.png", ""),
        ("https://foo.local/a.png", ""),
        ("https://intranet/a.png", ""),
        ("https://2130706433/a.png", ""),
        ("https://[::1]/a.png", ""),
        ("https://[64:ff9b::7f00:1]/a.png", ""),
        ("", ""),
    ],
)
def test_version_cover_url_only_accepts_public_https(value: str, expected: str):
    record = TaskboardVersionStoryUpdate(game="genshin", version="1.0", cover_url=value)
    assert record.cover_url == expected


def test_archived_image_url_keeps_existing_local_proxy():
    record = TaskboardArchivedActivity(
        id="1",
        game_key="bluearchive-cn",
        title="活动",
        image_url="http://127.0.0.1:36163/api/info/bluearchive/image?url=x",
    )
    assert record.image_url.startswith("http://127.0.0.1")
