# Copyright © 2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""回挑已合并 PR，并为发布分支保留正常的 PR 检查流程。"""

import json
import os
import re
import subprocess
from pathlib import Path


def run(*args, check=True):
    return subprocess.run(
        args, check=check, stdout=subprocess.PIPE, encoding="utf-8", errors="replace"
    )


def git(*args):
    return run("git", *args).stdout.rstrip("\n")


def release_targets(tags):
    """按数字版本选择最新正式版和最新公测版。"""
    latest = {}
    for tag in tags:
        match = re.fullmatch(r"v([0-9]+)\.([0-9]+)\.([0-9]+)(?:-beta\.([0-9]+))?", tag)
        if match is None:
            continue
        major, minor, patch, beta = match.groups()
        channel = "beta" if beta is not None else "stable"
        version = (int(major), int(minor), int(patch), int(beta or 0))
        if channel not in latest or version > latest[channel][0]:
            latest[channel] = version, tag
    if not latest:
        raise ValueError("没有找到正式版或公测版标签")
    return [f"release/{tag}" for _, tag in latest.values()]


def prepare_pick(target, sha, *, merge):
    """在目标分支快照上试挑，返回可发布的提交，或报告改动已存在。"""
    target_ref = f"origin/{target}"
    git("switch", "--detach", target_ref)
    if (
        run(
            "git", "merge-base", "--is-ancestor", sha, target_ref, check=False
        ).returncode
        == 0
    ):
        return None
    args = ["git", "cherry-pick", "-x", "--empty=drop"]
    if merge:
        args.extend(["-m", "1"])
    result = run(*args, sha, check=False)
    if result.returncode:
        paths = git("diff", "--name-only", "--diff-filter=U", "-z").split("\0")
        files = ", ".join(
            json.dumps(path, ensure_ascii=False) for path in paths if path
        )
        if files:
            git("cherry-pick", "--abort")
            raise ValueError(f"回挑到 {target} 时发生冲突，冲突文件：{files}")
        raise ValueError(f"回挑到 {target} 失败（git exit {result.returncode}）")
    commit = git("rev-parse", "HEAD")
    return commit if commit != git("rev-parse", target_ref) else None


def existing_pr(target, branch):
    result = run(
        "gh",
        "pr",
        "list",
        "--base",
        target,
        "--head",
        branch,
        "--state",
        "all",
        "--json",
        "url,state",
        "--limit",
        "1",
    )
    prs = json.loads(result.stdout)
    if not prs:
        return None
    pr = prs[0]
    if pr["state"] == "CLOSED":
        raise ValueError(f"{target} 的回挑 PR 已关闭且未合并：{pr['url']}")
    return pr["url"]


def publish_pr(target, branch, commit, pr, repository):
    remote_ref = f"refs/remotes/origin/{branch}"
    if (
        run(
            "git", "show-ref", "--verify", "--quiet", remote_ref, check=False
        ).returncode
        == 0
    ):
        if git("rev-parse", f"{remote_ref}^{{tree}}") != git(
            "rev-parse", f"{commit}^{{tree}}"
        ):
            raise ValueError(f"回挑分支 {branch} 已存在且内容不同")
    else:
        git("push", "origin", f"{commit}:refs/heads/{branch}")

    args = [
        "gh",
        "pr",
        "create",
        "--base",
        target,
        "--head",
        branch,
        "--title",
        f"fix(backport): 回挑 #{pr['number']} 到 {target}",
        "--body",
        f"自动回挑自 {repository}#{pr['number']}（`{pr['merge_commit_sha']}`）。",
    ]
    if any(label["name"] == "skip-changelog" for label in pr["labels"]):
        args.extend(["--label", "skip-changelog"])
    return run(*args).stdout.strip()


def backport(pr, repository):
    base = pr["base"]["ref"]
    prefix = {"main": "ci", "dev": "hotfix"}.get(base)
    if (
        not pr["merged"]
        or prefix is None
        or not re.match(rf"^{prefix}\([^()\r\n]+\)!?:\s", pr["title"])
    ):
        return []

    sha = pr["merge_commit_sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("缺少有效的 PR 合并提交 SHA")
    git("fetch", "--prune", "--tags", "origin", "+refs/heads/*:refs/remotes/origin/*")
    git("merge-base", "--is-ancestor", sha, f"origin/{base}")
    parents = git("show", "-s", "--format=%P", sha).split()
    if len(parents) == 1 and pr["commits"] > 1:
        rebase = run("gh", "api", f"repos/{repository}", "--jq", ".allow_rebase_merge")
        if rebase.stdout.strip() != "false":
            raise ValueError("仓库允许 rebase 合并，无法仅凭末尾 SHA 安全回挑多提交 PR")

    if base == "main":
        commit = prepare_pick("dev", sha, merge=len(parents) > 1)
        if commit is None:
            return ["`dev` 已包含本次改动。"]
        git("push", "origin", f"{commit}:refs/heads/dev")
        return [f"已回挑到 `dev`（`{commit[:12]}`）。"]

    changed = git("diff", "--name-only", "--no-renames", "-z", parents[0], sha)
    if any(
        path == "frontend" or path.startswith("frontend/")
        for path in changed.split("\0")
    ):
        raise ValueError("此 hotfix 包含 frontend 改动，发布分支不接收前端回挑")

    messages = []
    prepared = []
    for target in release_targets(git("tag", "--list").splitlines()):
        if run(
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{target}",
            check=False,
        ).returncode:
            raise ValueError(f"版本标签已存在，但缺少目标分支 {target}")
        branch = f"backport/pr-{pr['number']}/{target}"
        if url := existing_pr(target, branch):
            messages.append(f"`{target}` 已创建回挑 PR：{url}")
            continue
        commit = prepare_pick(target, sha, merge=len(parents) > 1)
        if commit is None:
            messages.append(f"`{target}` 已包含本次改动。")
        else:
            prepared.append((target, branch, commit))

    # 两个目标均完成试挑后才发布，避免一个目标冲突时留下半套新 PR。
    for target, branch, commit in prepared:
        url = publish_pr(target, branch, commit, pr, repository)
        messages.append(f"`{target}` 已创建回挑 PR：{url}")
    return messages


def main():
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    pr = event["pull_request"]
    try:
        messages = backport(pr, os.environ["GITHUB_REPOSITORY"])
    except (ValueError, subprocess.CalledProcessError) as error:
        message = f"PR #{pr['number']} 自动回挑失败：{error}"
        annotation = (
            message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        )
        print(f"::error::{annotation}", flush=True)
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open(
            "a", encoding="utf-8"
        ) as summary:
            summary.write(message + "\n")
        return 1
    for message in messages:
        print(message)
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open(
            "a", encoding="utf-8"
        ) as summary:
            summary.write(message + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
