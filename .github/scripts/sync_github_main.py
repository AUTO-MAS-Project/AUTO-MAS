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


def stage_github():
    """从 main 重建完整树，只替换 .github，同时同步 dev 中的删除。"""

    git("restore", "--source=origin/main", "--staged", "--worktree", ".")
    git("restore", "--source=origin/dev", "--staged", "--worktree", ".github")
    diff = git("diff", "--cached", "--name-only", "origin/main")
    if any(not path.startswith(".github/") for path in diff.splitlines()):
        raise RuntimeError("同步 PR 包含 .github 以外的改动")
    return diff


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

    diff = stage_github()

    owner = os.environ["GITHUB_REPOSITORY"].split("/")[0]
    if not diff:
        prs = github_request(f"pulls?state=open&base=main&head={owner}:{branch}")
        if prs:
            github_request(
                f"pulls/{prs[0]['number']}", method="PATCH", data={"state": "closed"}
            )
        report("dev/.github 与 main 一致，无需同步。")
        return

    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "ci: 同步 dev/.github 到 main")
    head_sha = git("rev-parse", "HEAD")
    git("push", "origin", f"HEAD:refs/heads/{branch}")
    body = "## 摘要\n\n- 仅同步 dev/.github 的新增、修改和删除。\n- 请维护者审核合并。"
    # 推送与维护者合并可能交错；每次都刷新 main 和开放 PR，不复用旧查询。
    for _ in range(3):
        git(
            "fetch",
            "--no-tags",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
        )
        if not git("diff", "--name-only", "origin/main", "HEAD", "--", ".github"):
            report("待同步的 .github 内容已进入 main，无需新建 PR。")
            return

        # 旧 PR 被 squash 合并后，接上新 main，避免新 PR 重复旧差异或冲突。
        if git("merge-base", "origin/main", "HEAD") != git("rev-parse", "origin/main"):
            git("merge", "--no-edit", "-s", "ours", "origin/main")
            stage_github()
            if git("diff", "--cached", "--name-only"):
                git("commit", "-m", "ci: 同步 dev/.github 到 main")
            head_sha = git("rev-parse", "HEAD")
            git("push", "origin", f"HEAD:refs/heads/{branch}")

        prs = github_request(f"pulls?state=open&base=main&head={owner}:{branch}")
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
        if pr["state"] != "open":
            continue
        if pr["head"]["sha"] != head_sha:
            raise RuntimeError("同步分支已被其他操作更新，请重新运行工作流")
        github_request(
            f"issues/{pr['number']}/labels",
            method="POST",
            data={"labels": ["skip-changelog"]},
        )
        current = github_request(f"pulls/{pr['number']}")
        if current["state"] == "open" and current["head"]["sha"] == head_sha:
            report(f"同步 PR：{current['html_url']}")
            return
    raise RuntimeError("同步期间 PR 状态持续变化，请重新运行工作流")


if __name__ == "__main__":
    sync_github()
