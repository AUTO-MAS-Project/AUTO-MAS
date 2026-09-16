from app.services.update import select_newer_version_info


def test_keeps_only_newer_versions_with_category_ownership():
    info = {
        "v5.5.0-beta.3": {"新增功能": ["a"], "修复BUG": ["b"]},
        "v5.5.0-beta.2": {"新增功能": ["c"]},
        "v5.4.0": {"新增功能": ["old"]},
    }

    result = select_newer_version_info(info, "v5.5.0-beta.2")

    assert result == {"v5.5.0-beta.3": {"新增功能": ["a"], "修复BUG": ["b"]}}


def test_sorts_by_packaging_version_not_string():
    info = {
        "v5.5.0-beta.2": {"x": ["2"]},
        "v5.5.0-beta.10": {"x": ["10"]},
        "v5.5.0": {"x": ["release"]},
        "v5.5.0-beta.3": {"x": ["3"]},
    }

    result = select_newer_version_info(info, "v5.5.0-beta.1")

    assert list(result) == [
        "v5.5.0",
        "v5.5.0-beta.10",
        "v5.5.0-beta.3",
        "v5.5.0-beta.2",
    ]


def test_returns_empty_when_nothing_newer():
    info = {"v5.5.0-beta.3": {"x": ["a"]}}

    assert select_newer_version_info(info, "v5.5.0-beta.3") == {}
    assert select_newer_version_info(info, "v5.5.0") == {}


def test_skips_keys_that_are_not_versions():
    """Mirror 酱的日志键不是版本号时只丢日志，不能让更新检查抛异常。"""

    info = {
        "placeholder": {"x": ["a"]},
        "v5.5.0-beta.3": {"新增功能": ["b"]},
        "release note": {"x": ["c"]},
    }

    assert select_newer_version_info(info, "v5.5.0-beta.2") == {
        "v5.5.0-beta.3": {"新增功能": ["b"]}
    }


def test_returns_empty_when_every_key_is_broken():
    info = {"placeholder": {}, "version": "oops"}

    assert select_newer_version_info(info, "v5.5.0-beta.1") == {}
