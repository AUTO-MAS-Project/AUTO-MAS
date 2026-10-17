# Copyright © 2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""仅将 dev/.github 同步到以 main 为目标的固定 PR。"""

import json
import os
import subprocess
import urllib.request
from pathlib import Path


def run(*args):
    return subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def git(*args):
    return run("git", *args)


def github_request(path, *, method="GET", data=None):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        data=None if data is None else json.dumps(data).encode(),
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = response.read()
        return json.loads(payload) if payload else None


def report(message):
    print(message)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")


def sync_github():
    branch = "codex/sync-github-main"
    git(
        "fetch",
        "--no-tags",
        "origin",
        "refs/heads/main:refs/remotes/origin/main",
        "refs/heads/dev:refs/remotes/origin/dev",
    )
    main_paths = set(
        git("ls-tree", "-r", "--name-only", "origin/main", "--", ".github").splitlines()
    )
    dev_paths = set(
        git("ls-tree", "-r", "--name-only", "origin/dev", "--", ".github").splitlines()
    )
    # 路径曾出现过不代表 main 当前的内容已迁移到 dev。
    unmigrated = []
    for path in sorted(main_paths - dev_paths):
        main_blob = git("rev-parse", f"origin/main:{path}")
        if not git(
            "log",
            "-1",
            "--format=%H",
            f"--find-object={main_blob}",
            "origin/dev",
            "--",
            path,
        ):
            unmigrated.append(path)
    if unmigrated:
        raise ValueError("main 独有的 CI 内容须先迁移到 dev：" + ", ".join(unmigrated))

    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    if remote:
        git(
            "fetch",
            "--no-tags",
            "origin",
            f"refs/heads/{branch}:refs/remotes/origin/{branch}",
        )
        git("checkout", "-B", branch, "origin/" + branch)
        git("merge", "--no-edit", "-s", "ours", "origin/main")
    else:
        git("checkout", "-b", branch, "origin/main")

    # 从 main 重建完整树，只替换 .github；同时同步 dev 中的删除。
    git("restore", "--source=origin/main", "--staged", "--worktree", ".")
    git("restore", "--source=origin/dev", "--staged", "--worktree", ".github")
    diff = git("diff", "--cached", "--name-only", "origin/main")
    if any(not path.startswith(".github/") for path in diff.splitlines()):
        raise RuntimeError("同步 PR 包含 .github 以外的改动")

    owner = os.environ["GITHUB_REPOSITORY"].split("/")[0]
    prs = github_request(f"pulls?state=open&base=main&head={owner}:{branch}")
    if not diff:
        if prs:
            github_request(
                f"pulls/{prs[0]['number']}", method="PATCH", data={"state": "closed"}
            )
        report("dev/.github 与 main 一致，无需同步。")
        return

    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "ci: 同步 dev/.github 到 main")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    body = "## 摘要\n\n- 仅同步 dev/.github 的新增、修改和删除。\n- 请维护者审核合并。"
    if prs:
        pr = github_request(
            f"pulls/{prs[0]['number']}", method="PATCH", data={"body": body}
        )
    else:
        pr = github_request(
            "pulls",
            method="POST",
            data={
                "head": branch,
                "base": "main",
                "title": "ci: 同步 dev/.github 到 main",
                "body": body,
            },
        )
    github_request(
        f"issues/{pr['number']}/labels",
        method="POST",
        data={"labels": ["skip-changelog"]},
    )
    report(f"同步 PR：{pr['html_url']}")


if __name__ == "__main__":
    sync_github()
