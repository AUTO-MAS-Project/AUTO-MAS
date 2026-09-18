import pytest
from loguru import logger as loguru_logger

from app.services.update import parse_release_note, select_newer_version_info

VALID_SECTION = {"新增功能": ["正常"]}


@pytest.fixture
def logged_warnings():
    """收集本次调用记下的警告（应用日志走 loguru，caplog 抓不到）。"""

    messages: list[str] = []

    def collect(message: str) -> None:
        messages.append(message)

    sink_id = loguru_logger.add(collect, level="WARNING", format="{message}")
    try:
        yield messages
    finally:
        loguru_logger.remove(sink_id)


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


@pytest.mark.parametrize(
    "broken_section",
    [
        {"新增功能": "字符串"},
        {"新增功能": 1},
        {"新增功能": {"嵌套": ["对象"]}},
        {"新增功能": [1]},
        {"新增功能": ["正常", {"嵌套": 1}]},
        {"新增功能": ["正常", None]},
    ],
    ids=[
        "category-is-str",
        "category-is-number",
        "category-is-object",
        "list-of-number",
        "list-mixed-object",
        "list-mixed-none",
    ],
)
def test_skips_sections_whose_shape_is_broken(broken_section):
    """版本段必须是「分类名 -> 字符串列表」，其它形状只丢该版本段。"""

    info = {"v5.5.0-beta.3": broken_section, "v5.5.0-beta.4": VALID_SECTION}

    assert select_newer_version_info(info, "v5.5.0-beta.2") == {
        "v5.5.0-beta.4": VALID_SECTION
    }


def test_skips_section_when_any_category_is_broken():
    """同一版本段里只要有一个分类形状不对，整个版本段都不能进响应。"""

    info = {"v5.5.0-beta.3": {"新增功能": ["正常"], "修复BUG": "字符串"}}

    assert select_newer_version_info(info, "v5.5.0-beta.2") == {}


def test_keeps_section_without_categories():
    """分类为空是合法形状，不因为空字典就丢掉整个版本段。"""

    info = {"v5.5.0-beta.3": {}}

    assert select_newer_version_info(info, "v5.5.0-beta.2") == {"v5.5.0-beta.3": {}}


def test_logs_warning_about_skipped_section(logged_warnings):
    """跳过时留一条 warning，说明跳掉的是哪个版本段、哪里不对。"""

    info = {"v5.5.0-beta.3": {"新增功能": "字符串"}}

    assert select_newer_version_info(info, "v5.5.0-beta.0") == {}

    assert any(
        "v5.5.0-beta.3" in message and "版本段结构异常" in message
        for message in logged_warnings
    )


def test_broken_sections_never_reach_the_response():
    """走一遍真实入参：Mirror 酱日志里的坏形状不能漏进更新检查结果。"""

    release_note = (
        '<!-- {"v5.5.0-beta.5": {"新增功能": ["好"]},'
        ' "v5.5.0-beta.4": {"新增功能": "字符串"},'
        ' "v5.5.0-beta.3": {"新增功能": ["好", 1]}} -->'
    )

    assert select_newer_version_info(
        parse_release_note(release_note), "v5.5.0-beta.2"
    ) == {"v5.5.0-beta.5": {"新增功能": ["好"]}}
