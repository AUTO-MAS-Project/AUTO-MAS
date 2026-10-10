#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找出 PR 删掉的、近期别人刚合入的代码行，提示可能是误回退。

在旧分支上改好文件、同步到新 dev 时整份带过去，会把这期间别人合入的改动一并盖掉：
git 看到的是 PR 自己的删除，合并没有冲突；类型检查也照样通过。#1043 就是这样悄悄
回退了 #755、#1007 的前端改动。

做法：取 PR 头与目标分支的合并基点，对 PR 删掉的每一行在合并基点上 blame，
来源提交在最近 N 天内合入、且作者不是本 PR 的作者，就按来源分组列出来。
只提示不拦截：改别人刚合入的代码本来也可能是有意的，由作者和审阅者确认。

为了少报，以下删除不算：
- 只改了空白或空行（``diff -w --ignore-blank-lines``，blame 同样忽略空白）；
- 只是换了折行：去掉空白、括号与逗号后，内容仍出现在同一文件新加的文本里
  （格式化工具拆行时会补括号和尾逗号，并行时会去掉）；
- 同一内容在本 PR 别的文件里又加回来（搬动代码）；
- 只有括号、标点之类没有字母数字的行；
- 由生成流程维护的文件（``CHANGELOG.md``、``res/version.json``、锁文件、``changelog.d/``）；
- 机器人提交与本 PR 作者自己的提交。

用法::

    python scripts/check_reverts.py --base origin/dev --head <PR 头提交> --author <PR 作者 login>
    python scripts/check_reverts.py ... --as-of 2026-09-26T14:52:46Z   # 按指定时刻判断「近期」，复现历史 PR 用

在 GitHub Actions 里运行时，结论写成 warning 注释（显示在 PR 的「Files changed」里）并写进
作业摘要；退出码恒为 0。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

IGNORED_FILES = ("CHANGELOG.md", "res/version.json", "uv.lock", "frontend/yarn.lock")
IGNORED_PREFIXES = ("changelog.d/",)
# 至少有一个字母、数字或汉字，才算有内容的行
MEANINGFUL = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
PR_NUMBER = re.compile(r"\(#(\d+)\)\s*$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
# 每个来源每个文件一条注释；GitHub 每个步骤只显示前 10 条 warning，其余看作业摘要
MAX_ANNOTATIONS = 10
MAX_LINES_SHOWN = 20


@dataclass
class Removed:
    path: str
    new_path: str
    old_line: int
    anchor: int  # 删除处在 PR 头文件里的行号，给注释定位；文件整个删掉时为 0
    content: str


@dataclass
class Source:
    sha: str
    author: str
    email: str
    committed: int
    summary: str
    lines: list[Removed] = field(default_factory=list)

    @property
    def label(self) -> str:
        match = PR_NUMBER.search(self.summary)
        return f"#{match.group(1)}" if match else self.sha[:9]

    @property
    def title(self) -> str:
        return PR_NUMBER.sub("", self.summary).strip()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def loose(text: str) -> str:
    """去掉空白、括号与逗号，用来认出只换了折行的格式化改动。"""

    return re.sub(r"[\s()\[\]{},]+", "", text)


def is_ignored(path: str) -> bool:
    return path in IGNORED_FILES or path.startswith(IGNORED_PREFIXES)


def removed_lines(base: str, head: str) -> list[Removed]:
    """PR 相对合并基点删掉的行（已去掉空白改动、搬动与无内容的行）。"""

    diff = git("diff", "-U0", "-w", "--ignore-blank-lines", "--no-color", base, head)
    removed: list[Removed] = []
    added_lines: set[str] = set()
    added_text: dict[str, list[str]] = {}
    old_path = new_path = ""
    old_no = anchor = 0
    in_header = False
    for raw in diff.splitlines():
        # 文件头只出现在 diff --git 与第一个 @@ 之间；hunk 里以 "-- " 开头的删除行
        # （如 SQL / Lua 注释）会显示成 "--- "，不能当成文件头
        if raw.startswith("diff --git "):
            in_header = True
            old_path = new_path = ""
        elif in_header and raw.startswith("--- "):
            old_path = (
                "" if raw == "--- /dev/null" else raw[len("--- a/") :].rstrip("\t")
            )
        elif in_header and raw.startswith("+++ "):
            new_path = (
                "" if raw == "+++ /dev/null" else raw[len("+++ b/") :].rstrip("\t")
            )
        elif raw.startswith("@@"):
            in_header = False
            match = HUNK.match(raw)
            if match:
                old_no = int(match.group(1))
                # 纯删除时 git 给的是删除位置的前一行；文件整个删掉时没有可定位的行
                anchor = max(int(match.group(3)), 1) if new_path else 0
        elif in_header:
            continue
        elif raw.startswith("-") and old_path:
            if not is_ignored(old_path):
                removed.append(Removed(old_path, new_path, old_no, anchor, raw[1:]))
            old_no += 1
        elif raw.startswith("+") and new_path:
            added_lines.add(loose(raw[1:]))
            added_text.setdefault(new_path, []).append(loose(raw[1:]))
    joined = {path: "".join(parts) for path, parts in added_text.items()}
    return [
        item
        for item in removed
        if MEANINGFUL.search(item.content)
        and loose(item.content) not in added_lines
        and loose(item.content) not in joined.get(item.new_path, "")
    ]


def blame(base: str, path: str, lines: list[int]) -> dict[int, dict[str, str]]:
    """在合并基点上 blame 指定行，返回 行号 -> 来源提交信息。"""

    ranges: list[str] = []
    start = prev = lines[0]
    for no in lines[1:] + [0]:
        if no == prev + 1:
            prev = no
            continue
        ranges += ["-L", f"{start},{prev}"]
        start = prev = no
    output = git("blame", "--porcelain", "-w", *ranges, base, "--", path)

    commits: dict[str, dict[str, str]] = {}
    result: dict[int, dict[str, str]] = {}
    current: dict[str, str] = {}
    final_line = 0
    for raw in output.splitlines():
        if raw.startswith("\t"):
            result[final_line] = current
            continue
        parts = raw.split(" ")
        if len(parts) >= 3 and len(parts[0]) == 40 and parts[1].isdigit():
            current = commits.setdefault(parts[0], {"sha": parts[0]})
            final_line = int(parts[2])
        elif parts[0] == "boundary":
            current["boundary"] = "1"
        elif parts[0] in ("author", "author-mail", "committer-time", "summary"):
            current[parts[0]] = raw.split(" ", 1)[1] if len(parts) > 1 else ""
    return result


def self_identity(base: str, head: str, login: str) -> tuple[set[str], set[str]]:
    """本 PR 作者可能用到的名字与邮箱：PR 自身提交里出现的，加上 GitHub 登录名。"""

    names = {login.casefold()} if login else set()
    emails: set[str] = set()
    for raw in git(
        "log", "--no-merges", "--format=%an%x00%ae", f"{base}..{head}"
    ).splitlines():
        name, _, email = raw.partition("\0")
        names.add(name.casefold())
        emails.add(email.casefold())
    return names, emails


def is_self(
    info: dict[str, str], names: set[str], emails: set[str], login: str
) -> bool:
    name = info.get("author", "").casefold()
    email = info.get("author-mail", "").strip("<>").casefold()
    if name in names or email in emails:
        return True
    login = login.casefold()
    noreply = f"{login}@users.noreply.github.com"
    return bool(login) and (email == noreply or email.endswith("+" + noreply))


def is_bot(info: dict[str, str]) -> bool:
    return info.get("author", "").endswith("[bot]") or "[bot]@" in info.get(
        "author-mail", ""
    )


def find_sources(
    base: str, head: str, login: str, days: int, as_of: datetime
) -> list[Source]:
    cutoff = as_of.timestamp() - days * 86400
    names, emails = self_identity(base, head, login)

    by_path: dict[str, list[Removed]] = {}
    for item in removed_lines(base, head):
        by_path.setdefault(item.path, []).append(item)

    sources: dict[str, Source] = {}
    for path, items in by_path.items():
        info_by_line = blame(base, path, sorted({item.old_line for item in items}))
        for item in items:
            info = info_by_line.get(item.old_line)
            if not info or info.get("boundary"):
                continue  # 浅克隆边界之外的行来源不可信，也必然不是近期的
            if int(info.get("committer-time", 0)) < cutoff:
                continue
            if is_bot(info) or is_self(info, names, emails, login):
                continue
            source = sources.setdefault(
                info["sha"],
                Source(
                    sha=info["sha"],
                    author=info.get("author", ""),
                    email=info.get("author-mail", ""),
                    committed=int(info.get("committer-time", 0)),
                    summary=info.get("summary", ""),
                ),
            )
            source.lines.append(item)
    return sorted(sources.values(), key=lambda s: s.committed)


def line_span(items: list[Removed]) -> str:
    numbers = sorted(item.old_line for item in items)
    spans: list[str] = []
    start = prev = numbers[0]
    for no in numbers[1:] + [0]:
        if no == prev + 1:
            prev = no
            continue
        spans.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = no
    return "、".join(spans)


def when(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    return escape_data(text).replace(":", "%3A").replace(",", "%2C")


def report(sources: list[Source], days: int) -> None:
    if not sources:
        print(f"没有发现删除近 {days} 天内他人合入代码的改动。")
        return

    annotations = 0
    for source in sources:
        files: dict[str, list[Removed]] = {}
        for item in source.lines:
            files.setdefault(item.path, []).append(item)
        print(
            f"\n{source.label}（{source.author}，{when(source.committed)} 合入）{source.title}"
        )
        for path, items in files.items():
            print(
                f"  {path} 删掉 {len(items)} 行（合并基点上第 {line_span(items)} 行）"
            )
            for item in items[:MAX_LINES_SHOWN]:
                print(f"    - {item.content.strip()}")
            if (
                os.environ.get("GITHUB_ACTIONS") == "true"
                and annotations < MAX_ANNOTATIONS
            ):
                annotations += 1
                title = f"可能回退了 {source.label} 的改动"
                message = (
                    f"这里删掉了 {source.label}（{source.author}，{when(source.committed)} 合入）"
                    f"加入的 {len(items)} 行（原第 {line_span(items)} 行）。"
                    "如果不是有意修改，多半是同步分支时带回了旧版本的文件。"
                )
                # 文件改了名就标在新路径上，整个删掉的文件只能标在旧路径上
                location = f"file={escape_property(items[0].new_path or path)}"
                if items[0].anchor:
                    location += f",line={items[0].anchor}"
                print(
                    f"::warning {location},title={escape_property(title)}::{escape_data(message)}"
                )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    out = [
        "## 删除了近期他人合入的代码",
        "",
        f"下面这些行是最近 {days} 天内由其他人合入的，本 PR 把它们删掉了。"
        "如果是有意修改，确认后忽略即可；如果不是，多半是在旧分支上改好文件、同步到新 dev 时"
        "整份带过来了，请把这些改动找回来。",
        "",
        "| 来源 | 作者 | 合入时间 | 文件 | 删掉的行 |",
        "|---|---|---|---|---|",
    ]
    for source in sources:
        files: dict[str, list[Removed]] = {}
        for item in source.lines:
            files.setdefault(item.path, []).append(item)
        for path, items in files.items():
            out.append(
                f"| {source.label} | {source.author} | {when(source.committed)} | "
                f"`{path}` | {len(items)} 行（原第 {line_span(items)} 行） |"
            )
    for source in sources:
        out += [
            "",
            f"<details><summary>{source.label} {source.title}</summary>",
            "",
            "```diff",
        ]
        for item in source.lines[:MAX_LINES_SHOWN]:
            out.append(f"-{item.content}")
        if len(source.lines) > MAX_LINES_SHOWN:
            out.append(f"# …… 还有 {len(source.lines) - MAX_LINES_SHOWN} 行")
        out += ["```", "", "</details>"]
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="目标分支，如 origin/dev")
    parser.add_argument("--head", required=True, help="PR 头提交")
    parser.add_argument("--author", default="", help="PR 作者的 GitHub 登录名")
    parser.add_argument(
        "--days", type=int, default=14, help="多少天内合入的算近期（默认 14）"
    )
    parser.add_argument("--as-of", help="按这个时刻判断近期（ISO 8601），默认现在")
    args = parser.parse_args()

    as_of = (
        datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if args.as_of
        else datetime.now(timezone.utc)
    )
    merge_base = git("merge-base", args.base, args.head).strip()
    sources = find_sources(merge_base, args.head, args.author, args.days, as_of)
    report(sources, args.days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
