"""scripts/changelog.py 的纯逻辑回归测试。

CHANGELOG.md 遵循 Keep a Changelog 1.1.0，是版本号与更新日志的唯一手写来源，
res/version.json 与另外四处版本号都由该脚本生成。解析器一旦跑偏，发布 CI 与合并后
补署名的机器人会一起跟着错，所以这里锁住解析、规范化与生成三件事。
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.utils.paths import SOURCE_ROOT


def _load_changelog_module() -> ModuleType:
    """scripts/ 不是包，按路径加载。"""

    script_path = SOURCE_ROOT / "scripts" / "changelog.py"
    spec = importlib.util.spec_from_file_location("changelog_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


changelog = _load_changelog_module()

MINIMAL = "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n- 甲\n"


def test_changelog_round_trips_to_itself() -> None:
    """仓库里的 CHANGELOG.md 已是规范形式：解析再渲染应逐字不变。"""

    original = changelog.read_text(changelog.CHANGELOG_PATH)
    _, sections, dates = changelog.parse_changelog(original)

    assert changelog.render_changelog(sections, dates) == original


def test_version_json_matches_changelog() -> None:
    """已提交的 res/version.json 必须是当前 CHANGELOG.md 的生成结果。"""

    current_version, sections, _ = changelog.parse_changelog(
        changelog.read_text(changelog.CHANGELOG_PATH)
    )

    assert changelog.render_version_json(
        current_version, sections
    ) == changelog.read_text(changelog.VERSION_JSON_PATH)


def test_version_json_carries_no_dates() -> None:
    """version.json 的结构是已发布客户端的解析契约，日期只留在 CHANGELOG.md 里。"""

    current_version, sections, _ = changelog.parse_changelog(
        changelog.read_text(changelog.CHANGELOG_PATH)
    )
    payload = changelog.json.loads(
        changelog.render_version_json(current_version, sections)
    )

    assert set(payload) == {"version", "version_info"}
    for categories in payload["version_info"].values():
        assert all(isinstance(items, list) for items in categories.values())


def test_current_version_is_the_first_section() -> None:
    """当前版本号取文件里第一个版本段，而不是最大的那个。"""

    current_version, sections, dates = changelog.parse_changelog(
        f"## [v9.9.9-beta.1] - {changelog.UNRELEASED}\n\n### 修复\n\n- 甲\n\n"
        "## [v9.9.8] - 2026-01-01\n\n### 修复\n\n- 乙\n"
    )

    assert current_version == "v9.9.9-beta.1"
    assert list(sections) == ["v9.9.9-beta.1", "v9.9.8"]
    assert dates["v9.9.9-beta.1"] == changelog.UNRELEASED


def test_preamble_prose_and_comments_are_skipped() -> None:
    """第一个版本标题之前是文件头说明，散文和注释都不该让解析失败。"""

    current_version, _, _ = changelog.parse_changelog(
        "# 更新日志\n\n本项目所有值得注意的变更都记录在此文件中。\n\n"
        "格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。\n\n"
        "<!-- 贡献者须知 -->\n\n" + MINIMAL
    )

    assert current_version == "v1.0.0"


def test_link_definitions_are_ignored_on_parse() -> None:
    """底部的版本对比链接由 render 重新生成，解析时不能被当成条目。"""

    _, sections, _ = changelog.parse_changelog(
        MINIMAL + "\n[v1.0.0]: https://example.invalid/releases/tag/v1.0.0\n"
    )

    assert sections == {"v1.0.0": {"修复": ["甲"]}}


def test_links_compare_against_the_previous_listed_version() -> None:
    """未发布版本对到开发分支，最老的一版指向自己的 Release 页。"""

    _, sections, dates = changelog.parse_changelog(
        f"## [v2.0.0] - {changelog.UNRELEASED}\n\n### 修复\n\n- 甲\n\n"
        "## [v1.5.0] - 2026-01-02\n\n### 修复\n\n- 乙\n\n"
        "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n- 丙\n"
    )

    assert changelog.render_links(sections, dates) == [
        f"[v2.0.0]: {changelog.REPO_URL}/compare/v1.5.0...{changelog.DEVELOPMENT_BRANCH}",
        f"[v1.5.0]: {changelog.REPO_URL}/compare/v1.0.0...v1.5.0",
        f"[v1.0.0]: {changelog.REPO_URL}/releases/tag/v1.0.0",
    ]


def test_unreleased_is_only_allowed_at_the_top() -> None:
    """已发布的版本段必须带真实日期，否则发布链路取不到发布时间。"""

    with pytest.raises(changelog.ChangelogError, match="只有文件顶部"):
        changelog.parse_changelog(
            "## [v2.0.0] - 2026-01-02\n\n### 修复\n\n- 甲\n\n"
            f"## [v1.0.0] - {changelog.UNRELEASED}\n\n### 修复\n\n- 乙\n"
        )


def test_duplicate_entry_is_rejected() -> None:
    """同一分类下重复登记同一条会直接报错，避免更新日志里出现两条一样的。"""

    with pytest.raises(changelog.ChangelogError, match="条目重复"):
        changelog.parse_changelog(
            "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n- 同一条\n- 同一条\n"
        )


def test_free_text_line_is_rejected() -> None:
    """条目之外的散文会被拒绝，保证文件始终能无损转成 version.json。"""

    with pytest.raises(changelog.ChangelogError, match="无法识别的内容"):
        changelog.parse_changelog(
            "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n随手写的一段说明\n"
        )


def test_comment_inside_a_version_section_is_rejected() -> None:
    """版本段里的注释不会被 render 保留，写了就会被 sync 悄悄删掉。"""

    with pytest.raises(changelog.ChangelogError, match="不能写注释"):
        changelog.parse_changelog(
            "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n<!-- 顺手记一笔 -->\n\n- 甲\n"
        )


def test_indented_entry_is_rejected() -> None:
    """嵌套列表转不成 version.json，扁平化会悄悄改变原意。"""

    with pytest.raises(changelog.ChangelogError, match="不能缩进"):
        changelog.parse_changelog(
            "## [v1.0.0] - 2026-01-01\n\n### 修复\n\n- 甲\n  - 子项\n"
        )


def test_bom_is_stripped_on_read(tmp_path) -> None:
    """记事本存出来的 BOM 不该让整份文件解析失败。"""

    path = tmp_path / "CHANGELOG.md"
    path.write_text(MINIMAL, encoding="utf-8-sig", newline="\n")

    current_version, _, _ = changelog.parse_changelog(changelog.read_text(path))

    assert current_version == "v1.0.0"


@pytest.mark.parametrize(
    "heading",
    [
        "## v1.0.0",  # 少了方括号与日期
        "## [v1.0.0]",  # 少了日期
        "## [1.0.0] - 2026-01-01",  # 少了 v 前缀
        "## [v1.0.0] - 2026/01/01",  # 日期不是 ISO 8601
        "## [v1.0.0] - 明天",
    ],
)
def test_invalid_release_heading_is_rejected(heading: str) -> None:
    with pytest.raises(changelog.ChangelogError, match="版本标题|版本号"):
        changelog.parse_changelog(f"{heading}\n\n### 修复\n\n- 甲\n")


def test_known_categories_are_ordered_and_unknown_ones_kept() -> None:
    """置顶两类排在最前，Keep a Changelog 六类按规范顺序，表外分类排在最后。"""

    ordered = changelog.order_categories(
        {
            "开发流程": ["己"],
            "修复": ["丁"],
            "自定义分类": ["庚"],
            "新增": ["丙"],
            "本次亮点": ["乙"],
            "破坏性变更": ["甲"],
            "安全": ["戊"],
        }
    )

    assert list(ordered) == [
        "破坏性变更",
        "本次亮点",
        "新增",
        "修复",
        "安全",
        "开发流程",
        "自定义分类",
    ]


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v5.5.0-beta.3", "5.5.0b3"),
        ("v5.5.0-alpha.1", "5.5.0a1"),
        ("v5.5.0-rc.2", "5.5.0rc2"),
        ("v5.4.0", "5.4.0"),
        ("v5.5.10-beta.10", "5.5.10b10"),
    ],
)
def test_to_pep440(tag: str, expected: str) -> None:
    assert changelog.to_pep440(tag) == expected


def test_to_pep440_rejects_unsupported_shape() -> None:
    with pytest.raises(changelog.ChangelogError, match="PEP 440"):
        changelog.to_pep440("v5.5.0-dev")


# ---------------------------------------------------------------------------
# 碎片、版本号推进、发版编译、Release 正文
# ---------------------------------------------------------------------------


def _fragment(tmp_path: Path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="\n")
    return changelog.parse_fragment(path, changelog.read_text(path))


def test_fragment_name_decides_category_and_body_is_one_line(tmp_path) -> None:
    fragment = _fragment(tmp_path, "683.feat.md", "模拟器管理 MuMu 新增开关\n")

    assert fragment.identifier == "683"
    assert fragment.category == "新增"
    assert fragment.text == "模拟器管理 MuMu 新增开关"
    assert fragment.author is None


def test_fragment_accepts_author_override_and_leading_dash(tmp_path) -> None:
    fragment = _fragment(
        tmp_path, "mumu-kill.fix.md", "author: @HarcoChen\n\n- 修复了一个问题\n"
    )

    assert fragment.author == "HarcoChen"
    assert fragment.text == "修复了一个问题"
    assert fragment.category == "修复"


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("683.md", "甲\n", "文件名"),  # 没有分类后缀
        ("683.feature.md", "甲\n", "文件名"),  # 未知分类
        ("683.feat.md", "\n", "为空"),
        ("683.feat.md", "甲\n乙\n", "只能有一行"),
        ("683.feat.md", "甲 by [@a](https://github.com/a)\n", "署名"),
        ("683.feat.md", "author: a\nauthor: b\n甲\n", "author 只能写一次"),
    ],
)
def test_invalid_fragment_is_rejected(tmp_path, name, content, message) -> None:
    with pytest.raises(changelog.ChangelogError, match=message):
        _fragment(tmp_path, name, content)


def test_list_fragments_skips_readme_and_rejects_strangers(tmp_path) -> None:
    (tmp_path / "README.md").write_text("说明", encoding="utf-8")
    (tmp_path / "1.fix.md").write_text("甲\n", encoding="utf-8")

    assert [f.identifier for f in changelog.list_fragments(tmp_path)] == ["1"]

    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(changelog.ChangelogError, match="文件名"):
        changelog.list_fragments(tmp_path)


@pytest.mark.parametrize(
    ("kind", "latest", "explicit", "expected"),
    [
        ("beta", "v5.5.0-beta.6", None, "v5.5.0-beta.7"),
        ("beta", "v5.5.0", None, "v5.6.0-beta.1"),
        ("beta", "v5.5.1", None, "v5.6.0-beta.1"),
        ("stable", "v5.5.0-beta.7", None, "v5.5.0"),
        ("patch", "v5.5.0", None, "v5.5.1"),
        ("patch", "v5.5.1", None, "v5.5.2"),
        ("explicit", "v5.5.0", "v6.0.0-beta.1", "v6.0.0-beta.1"),
    ],
)
def test_next_version_follows_the_rules(kind, latest, explicit, expected) -> None:
    assert changelog.next_version(kind, latest, explicit) == expected


@pytest.mark.parametrize(
    ("kind", "latest", "explicit", "message"),
    [
        ("stable", "v5.5.0", None, "已经是正式版"),  # 转正只能从 beta 出
        ("patch", "v5.5.0-beta.3", None, "预发布版"),  # 补丁只能从正式版出
        ("explicit", "v5.5.0", "v5.5.0", "没有大于"),  # 不许复用
        ("explicit", "v5.5.0", "v5.4.9", "没有大于"),  # 不许倒退
        ("explicit", "v5.5.0", "5.5.1", "不合形态"),
        ("beta", None, None, "找不到任何"),
    ],
)
def test_next_version_rejects_wrong_moves(kind, latest, explicit, message) -> None:
    with pytest.raises(changelog.ChangelogError, match=message):
        changelog.next_version(kind, latest, explicit)


def test_latest_version_orders_like_semver_and_skips_odd_tags() -> None:
    tags = [
        "v5.5.0-beta.9",
        "v5.5.0-beta.10",
        "v5.4.0",
        "v5.4.0-dev-nte-plus-hsr",  # 不合形态，忽略
        "mfw-m9a-fixes-checkpoint",
    ]

    assert changelog.latest_version(tags) == "v5.5.0-beta.10"
    assert changelog.latest_version(["v5.5.0-beta.10", "v5.5.0"]) == "v5.5.0"
    assert changelog.latest_version(["v5.5.0", "v5.5.1-beta.1"]) == "v5.5.1-beta.1"
    assert changelog.latest_version(["x"]) is None


def test_signatures_split_join_and_merge() -> None:
    entry = "甲 by [@a](https://github.com/a) by [@b](https://github.com/b)"

    assert changelog.split_signatures(entry) == ("甲", ["a", "b"])
    assert changelog.join_signatures("甲", ["a", "a", "b"]) == entry
    # 旧机器人给多人条目补的署名只有第一个带 by，后面用空格连着；正文中间的链接不算署名
    legacy = "甲 by [@a](https://github.com/a) [@b](https://github.com/b)"
    assert changelog.split_signatures(legacy) == ("甲", ["a", "b"])
    mention = "甲 by [@a](https://github.com/a) 报告的问题"
    assert changelog.split_signatures(mention) == (mention, [])

    target = {"修复": [entry]}
    changelog.merge_entries(
        target, {"修复": ["甲 by [@c](https://github.com/c)", "乙"], "新增": ["丙"]}
    )

    assert target == {
        "修复": [
            "甲 by [@a](https://github.com/a) by [@b](https://github.com/b)"
            " by [@c](https://github.com/c)",
            "乙",
        ],
        "新增": ["丙"],
    }


def _sections(text: str):
    _, sections, dates = changelog.parse_changelog(text)
    return sections, dates


def test_compile_beta_absorbs_the_pending_unreleased_section(tmp_path) -> None:
    """过渡期顶部手工预留的「未发布」段并入新段，编号以计算结果为准。"""

    sections, dates = _sections(
        f"## [v5.5.0-beta.6] - {changelog.UNRELEASED}\n\n### 修复\n\n- 甲\n\n"
        "## [v5.5.0-beta.5] - 2026-09-12\n\n### 新增\n\n- 乙\n"
    )
    fragment = _fragment(tmp_path, "700.feat.md", "丙\n")

    new_sections, new_dates = changelog.compile_release(
        sections,
        dates,
        [fragment],
        "v5.5.0-beta.6",
        "2026-09-13",
        {"700.feat.md": "qiyinxi"},
        tagged=["v5.5.0-beta.5"],
    )

    assert list(new_sections) == ["v5.5.0-beta.6", "v5.5.0-beta.5"]
    assert new_dates["v5.5.0-beta.6"] == "2026-09-13"
    assert new_sections["v5.5.0-beta.6"] == {
        "新增": ["丙 by [@qiyinxi](https://github.com/qiyinxi)"],
        "修复": ["甲"],
    }


def test_compile_stable_rolls_up_the_whole_beta_cycle(tmp_path) -> None:
    """转正时同号的 beta 段全部并入正式版段并从文件里移除，其他版本不动。"""

    sections, dates = _sections(
        "## [v5.5.0-beta.2] - 2026-09-02\n\n### 修复\n\n"
        "- 甲 by [@a](https://github.com/a)\n- 乙\n\n"
        "## [v5.5.0-beta.1] - 2026-09-01\n\n### 新增\n\n- 丙\n\n### 修复\n\n"
        "- 己\n- 甲\n\n"
        "## [v5.4.0] - 2026-08-26\n\n### 新增\n\n- 丁\n"
    )
    fragment = _fragment(tmp_path, "9.fix.md", "戊\n")

    new_sections, new_dates = changelog.compile_release(
        sections,
        dates,
        [fragment],
        "v5.5.0",
        "2026-09-13",
        {"9.fix.md": None},
        tagged=[],
    )

    assert list(new_sections) == ["v5.5.0", "v5.4.0"]
    # 从旧到新并入：beta.1 独有的己排最前，倒过来并入的话乙会跑到己前面；
    # 甲在两个 beta 里都有，只留一条且署名保留
    assert new_sections["v5.5.0"] == {
        "新增": ["丙"],
        "修复": ["己", "甲 by [@a](https://github.com/a)", "乙", "戊"],
    }
    assert new_dates == {"v5.5.0": "2026-09-13", "v5.4.0": "2026-08-26"}


def test_compile_reopens_an_untagged_section_but_not_a_tagged_one(tmp_path) -> None:
    """发版 PR 合并后又来了改动：同号还没打 tag 就在原段上追加，打过 tag 就拒绝。"""

    sections, dates = _sections(
        "## [v5.5.0-beta.7] - 2026-09-13\n\n### 修复\n\n- 甲\n\n"
        "## [v5.5.0-beta.6] - 2026-09-12\n\n### 修复\n\n- 乙\n"
    )
    fragment = _fragment(tmp_path, "10.fix.md", "丙\n")

    new_sections, _ = changelog.compile_release(
        sections,
        dates,
        [fragment],
        "v5.5.0-beta.7",
        "2026-09-14",
        {},
        tagged=["v5.5.0-beta.6"],
    )
    assert new_sections["v5.5.0-beta.7"] == {"修复": ["甲", "丙"]}

    with pytest.raises(changelog.ChangelogError, match="已经发布过"):
        changelog.compile_release(
            sections,
            dates,
            [fragment],
            "v5.5.0-beta.7",
            "2026-09-14",
            {},
            tagged=["v5.5.0-beta.6", "v5.5.0-beta.7"],
        )


def test_compile_refuses_to_go_backwards_or_publish_nothing(tmp_path) -> None:
    sections, dates = _sections("## [v5.5.0-beta.6] - 2026-09-12\n\n### 修复\n\n- 乙\n")

    with pytest.raises(changelog.ChangelogError, match="没有任何可发布"):
        changelog.compile_release(
            sections, dates, [], "v5.5.0-beta.7", "2026-09-13", {}, []
        )

    fragment = _fragment(tmp_path, "1.fix.md", "甲\n")
    with pytest.raises(changelog.ChangelogError, match="不能倒退"):
        changelog.compile_release(
            sections, dates, [fragment], "v5.5.0-beta.5", "2026-09-13", {}, []
        )


FULL_HISTORY = (
    "## [v5.6.0] - 2026-10-10\n\n### 新增\n\n- 庚\n\n"
    "## [v5.6.0-beta.2] - 2026-10-02\n\n### 修复\n\n- 己\n\n"
    "## [v5.6.0-beta.1] - 2026-10-01\n\n### 新增\n\n- 戊\n\n"
    "## [v5.5.1] - 2026-09-20\n\n### 修复\n\n- 丁 by [@b](https://github.com/b)\n\n"
    "## [v5.5.0] - 2026-09-15\n\n### 新增\n\n- 丙 by [@a](https://github.com/a)\n\n"
    "## [v5.4.0] - 2026-08-26\n\n### 新增\n\n- 乙\n\n"
    "## [v5.3.0] - 2026-06-07\n\n### 新增\n\n- 甲\n"
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        # 公测：本周期全部 beta 段 + 上一个正式周期整条线（补丁与 X.Y.0 汇总都在）
        ("v5.6.0-beta.2", ["v5.6.0-beta.2", "v5.6.0-beta.1", "v5.5.1", "v5.5.0"]),
        # 转正：本次 + 上一个正式周期整条线，不带 beta 段
        ("v5.6.0", ["v5.6.0", "v5.5.1", "v5.5.0"]),
        ("v5.5.0", ["v5.5.0", "v5.4.0"]),
        # 补丁：本次 + 同一 X.Y 下的正式版
        ("v5.5.1", ["v5.5.1", "v5.5.0"]),
    ],
)
def test_release_note_json_carries_the_right_sections(version, expected) -> None:
    sections, _ = _sections(FULL_HISTORY)

    assert changelog.select_note_versions(sections, version) == expected


def test_release_note_has_contract_first_line_contributors_and_compare_link() -> None:
    sections, _ = _sections(FULL_HISTORY)

    note = changelog.render_release_note(sections, "v5.5.0")
    first, rest = note.split("\n", 1)

    assert first.startswith("<!--") and first.endswith("-->")
    payload = json.loads(first[4:-3])
    assert list(payload) == ["v5.5.0", "v5.4.0"]
    assert payload["v5.5.0"] == {"新增": ["丙 by [@a](https://github.com/a)"]}
    assert "## v5.5.0" in rest
    assert "### 贡献者\n\n[@a](https://github.com/a)" in rest
    # 正式版对比上一个正式版；补丁与公测对比紧邻的上一段
    assert "compare/v5.4.0...v5.5.0" in rest
    assert "compare/v5.5.0...v5.5.1" in changelog.render_release_note(
        sections, "v5.5.1"
    )
    assert "compare/v5.6.0-beta.1...v5.6.0-beta.2" in changelog.render_release_note(
        sections, "v5.6.0-beta.2"
    )


# ---------------------------------------------------------------------------
# 需要真实 git 仓库的部分：PR 级检查、署名来源、待确认提交
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _commit(
    root: Path,
    message: str,
    author: str = "Dev <1+dev@users.noreply.github.com>",
) -> str:
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=Dev",
        "-c",
        "user.email=dev@example.com",
        "commit",
        "-q",
        "-m",
        message,
        f"--author={author}",
    )
    return _git(root, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """一个带 dev 分支、一个 tag 和五处版本文件的最小仓库，版本号 v1.0.0-beta.1。"""

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "dev")
    _write(
        root, "CHANGELOG.md", "## [v1.0.0-beta.1] - 2026-01-01\n\n### 修复\n\n- 甲\n"
    )
    _write(root, "res/version.json", "{}\n")
    _write(root, "frontend/package.json", '{\n  "version": "v1.0.0-beta.1"\n}\n')
    _write(root, "app/core/config.py", '    VERSION = "v1.0.0-beta.1"\n')
    _write(root, "pyproject.toml", 'version = "1.0.0b1"\n')
    _write(root, "uv.lock", '[[package]]\nname = "auto-mas"\nversion = "1.0.0b1"\n')
    _write(root, "changelog.d/README.md", "说明\n")
    _write(root, "app/x.py", "x = 1\n")
    _commit(root, "chore: init")
    _git(root, "tag", "v1.0.0-beta.1")
    return root


def _branch(root: Path, name: str) -> None:
    _git(root, "checkout", "-q", "-b", name)


def _check(root: Path, base: str, kind: str = "normal", **flags):
    return changelog.check_pull_request(
        base,
        kind,
        flags.get("skip", False),
        flags.get("maintenance", False),
        flags.get("dev_ref"),
        root=root,
    )


def test_pr_check_accepts_one_fragment_for_a_user_visible_change(repo) -> None:
    _branch(repo, "feat/x")
    _write(repo, "app/x.py", "x = 2\n")
    _write(repo, "changelog.d/feat-x.feat.md", "新功能\n")
    _commit(repo, "feat: x")

    assert _check(repo, "dev") == []


def test_pr_check_requires_a_fragment_unless_skipped(repo) -> None:
    _branch(repo, "feat/x")
    _write(repo, "app/x.py", "x = 2\n")
    _commit(repo, "feat: x")

    assert any("没有新增更新日志碎片" in p for p in _check(repo, "dev"))
    assert _check(repo, "dev", skip=True) == []


def test_pr_check_ignores_non_user_visible_changes(repo) -> None:
    _branch(repo, "docs/x")
    _write(repo, "README.md", "文档\n")
    _commit(repo, "docs: x")

    assert _check(repo, "dev") == []


def test_pr_check_rejects_two_fragments_and_touching_others(repo) -> None:
    _write(repo, "changelog.d/other.fix.md", "别人的\n")
    _commit(repo, "fix: other")
    _branch(repo, "feat/x")
    _write(repo, "changelog.d/a.feat.md", "甲\n")
    _write(repo, "changelog.d/b.fix.md", "乙\n")
    (repo / "changelog.d/other.fix.md").unlink()
    _commit(repo, "feat: x")

    problems = _check(repo, "dev")
    assert any("只放一个碎片" in p for p in problems)
    assert any("不要修改或删除已有的碎片" in p for p in problems)


def test_pr_check_blocks_changelog_and_version_edits_in_normal_prs(repo) -> None:
    _branch(repo, "feat/x")
    _write(
        repo,
        "CHANGELOG.md",
        "## [v1.0.0-beta.2] - 未发布\n\n### 修复\n\n- 乙\n\n"
        "## [v1.0.0-beta.1] - 2026-01-01\n\n### 修复\n\n- 甲\n",
    )
    _write(repo, "pyproject.toml", 'version = "1.0.0b2"\n')
    _write(repo, "app/core/config.py", '    VERSION = "v1.0.0-beta.2"\n    OTHER = 1\n')
    _commit(repo, "feat: bump")

    joined = "\n".join(_check(repo, "dev", skip=True))
    assert "不能改 CHANGELOG.md" in joined
    assert "pyproject.toml 里的版本号" in joined
    assert "app/core/config.py 里的版本号" in joined
    # 打了 changelog-maintenance 标签就放行
    assert _check(repo, "dev", skip=True, maintenance=True) == []


def test_pr_check_allows_code_edits_next_to_an_unchanged_version(repo) -> None:
    _branch(repo, "feat/x")
    _write(repo, "app/core/config.py", '    VERSION = "v1.0.0-beta.1"\n    OTHER = 1\n')
    _write(repo, "changelog.d/x.change.md", "调整\n")
    _commit(repo, "feat: x")

    assert _check(repo, "dev") == []


def test_pr_check_release_kind_needs_empty_fragments_and_a_bump(repo) -> None:
    _write(repo, "changelog.d/x.fix.md", "乙\n")
    _commit(repo, "fix: x")
    _branch(repo, "chore/release")
    _write(
        repo,
        "CHANGELOG.md",
        "## [v1.0.0-beta.2] - 2026-01-02\n\n### 修复\n\n- 乙\n\n"
        "## [v1.0.0-beta.1] - 2026-01-01\n\n### 修复\n\n- 甲\n",
    )
    _commit(repo, "chore(release): v1.0.0-beta.2")

    assert any("必须已经清空" in p for p in _check(repo, "dev", "release"))

    (repo / "changelog.d/x.fix.md").unlink()
    _commit(repo, "chore(release): clean")
    assert _check(repo, "dev", "release") == []


def test_pr_check_flags_dev_only_commits_leaking_into_release(repo) -> None:
    """从 dev 切的分支合进 release 会带走一堆 dev 提交（#673 那种事故）。"""

    _git(repo, "branch", "release/v1.0.0-beta.1")
    _write(repo, "app/x.py", "x = 2\n")
    _write(repo, "changelog.d/1.fix.md", "dev 上的改动\n")
    _commit(repo, "feat: only on dev")
    # 错误做法：直接从 dev 开分支修 release
    _branch(repo, "fix/wrong")
    _write(repo, "app/y.py", "y = 1\n")
    _write(repo, "changelog.d/2.fix.md", "热修\n")
    _commit(repo, "fix: hot")

    problems = _check(repo, "release/v1.0.0-beta.1", dev_ref="dev")
    assert any("只在 dev 上的提交" in p for p in problems)
    # 发版 PR 被误改目标到 release/* 时同样要拦，不能因为类型分流而跳过
    release_problems = _check(repo, "release/v1.0.0-beta.1", "release", dev_ref="dev")
    assert any("只在 dev 上的提交" in p for p in release_problems)

    # 正确做法：基于 release 分支 cherry-pick
    _git(repo, "checkout", "-q", "release/v1.0.0-beta.1")
    _branch(repo, "fix/right")
    _git(
        repo,
        "-c",
        "user.name=Dev",
        "-c",
        "user.email=dev@example.com",
        "cherry-pick",
        "fix/wrong",
    )
    assert _check(repo, "release/v1.0.0-beta.1", dev_ref="dev") == []


def test_version_floor_catches_a_clobbered_bump(repo) -> None:
    assert changelog.check_version_floor("v1.0.0-beta.1", root=repo) == "v1.0.0-beta.1"
    assert changelog.check_version_floor("v1.0.0-beta.2", root=repo) == "v1.0.0-beta.1"
    with pytest.raises(changelog.ChangelogError, match="小于已发布的 tag"):
        changelog.check_version_floor("v0.9.0", root=repo)


def test_fragment_author_comes_from_the_commit_that_added_it(repo) -> None:
    """noreply 邮箱直接拆出登录名；author 行覆盖一切；不读 Co-authored-by。"""

    _write(repo, "changelog.d/1.fix.md", "甲\n")
    _commit(
        repo,
        "fix: a\n\nCo-authored-by: Robot <robot@example.com>",
        author="Alice <123+alice@users.noreply.github.com>",
    )
    _write(repo, "changelog.d/2.fix.md", "author: bob\n乙\n")
    _commit(repo, "fix: b", author="Carol <carol@example.com>")
    _write(repo, "changelog.d/3.fix.md", "丙\n")
    _commit(repo, "fix: c", author="Carol <carol@example.com>")
    _write(repo, "changelog.d/4.fix.md", "丁\n")
    _commit(repo, "fix: d", author="Carol Chen <carol@example.com>")
    _write(repo, "changelog.d/5.fix.md", "戊\n")
    _commit(repo, "fix: e", author="寒风 <hanfeng@example.com>")
    fragments = {
        f.identifier: f for f in changelog.list_fragments(repo / "changelog.d")
    }

    author = changelog.fragment_author
    assert author(fragments["1"], root=repo, resolve_online=False) == "alice"
    assert author(fragments["2"], root=repo, resolve_online=False) == "bob"
    # 解析不到登录名时，git 作者名长得像登录名才拿来用
    assert author(fragments["3"], root=repo, resolve_online=False) == "Carol"
    # 带空格的全名、中文昵称都不是登录名，签进去会变成坏链接，宁可不署名
    assert author(fragments["4"], root=repo, resolve_online=False) is None
    assert author(fragments["5"], root=repo, resolve_online=False) is None


def test_fragment_author_follows_the_latest_addition_after_reuse(repo) -> None:
    """碎片发版后被删，同名文件被别人再次新增，署名要归后来的人。"""

    _write(repo, "changelog.d/fix-x.fix.md", "甲\n")
    _commit(repo, "fix: a", author="Alice <1+alice@users.noreply.github.com>")
    (repo / "changelog.d/fix-x.fix.md").unlink()
    _commit(repo, "chore(release): v1.0.0-beta.2")
    _write(repo, "changelog.d/fix-x.fix.md", "乙\n")
    _commit(repo, "fix: b", author="Bob <2+bob@users.noreply.github.com>")
    fragment = changelog.list_fragments(repo / "changelog.d")[0]

    assert changelog.fragment_author(fragment, root=repo, resolve_online=False) == "bob"


def test_unconfirmed_commits_lists_user_visible_pushes_without_fragments(repo) -> None:
    _write(repo, "app/x.py", "x = 2\n")
    _commit(repo, "fix: 直推没带碎片")
    _write(repo, "app/x.py", "x = 3\n")
    _write(repo, "changelog.d/9.fix.md", "带了\n")
    _commit(repo, "fix: 带了碎片")
    _write(repo, "README.md", "文档\n")
    _commit(repo, "fix: 只改文档")
    _write(repo, "app/x.py", "x = 4\n")
    _commit(repo, "chore: 重构")

    subjects = [s for _, s in changelog.unconfirmed_commits("v1.0.0-beta.1", root=repo)]

    assert subjects == ["fix: 直推没带碎片"]
