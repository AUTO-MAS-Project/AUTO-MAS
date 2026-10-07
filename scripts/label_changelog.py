#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""读取 PR 碎片，同步分类与项目标签；不检出、不执行 PR 代码。"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from changelog import (
    FRAGMENT_IGNORED,
    FRAGMENT_NAME,
    PROJECTS,
    ChangelogError,
    parse_fragment,
)

TYPE_LABELS = {
    "breaking": "类型: 破坏性变更",
    "feat": "类型: 新增",
    "change": "类型: 变更",
    "remove": "类型: 移除",
    "fix": "类型: 修复",
    "security": "类型: 安全",
    "dev": "类型: 开发流程",
}
# 沿用仓库已有专项标签；本体功能使用「模块:」前缀。
MODULE_PROJECTS = {
    "home",
    "scheduler",
    "emulator",
    "notify",
    "tools",
    "settings",
    "update",
    "runtime",
}
PROJECT_LABELS = {
    key: f"{'模块' if key in MODULE_PROJECTS else '专项'}: {name}"
    for key, name in PROJECTS.items()
}
PROJECT_LABELS.update(
    {"end": "专项: MaaEnd", "bgi": "专项: BetterGI", "mfw": "专项: MaaFW"}
)
MANAGED_LABELS = set(TYPE_LABELS.values()) | set(PROJECT_LABELS.values())


def github_api(
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    paginate: bool = False,
) -> Any:
    """通过 runner 的 gh 调用 API，参数和 PR 内容不经过 shell。"""

    command = ["gh", "api", "--method", method, endpoint]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def api_error(error: subprocess.CalledProcessError) -> str:
    """把 gh 的报错压成一行，方便放进工作流注解里。"""

    detail = (error.stderr or "").strip() or (error.stdout or "").strip()
    return detail.replace("\n", " ") or f"退出码 {error.returncode}"


def fragment_labels(filename: str, content: str) -> set[str]:
    """复用入账解析器，亮点和仅公测标记不改变碎片原分类。"""

    fragment = parse_fragment(Path(filename), content)
    matched = FRAGMENT_NAME.fullmatch(fragment.path.name)
    assert matched is not None
    labels = {TYPE_LABELS[matched.group("type")]}
    if fragment.project:
        labels.add(PROJECT_LABELS[fragment.project])
    return labels


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    number = int(os.environ["PR_NUMBER"])
    endpoint = f"repos/{repo}/pulls/{number}"
    pr = github_api(endpoint)
    if pr["state"] != "open":
        return
    # 重新读取当前 PR，而非旧事件中的 SHA；排队期间更新过也按最新碎片同步。
    head_sha = pr["head"]["sha"]
    head_repo = pr["head"]["repo"]["full_name"]
    pages = github_api(f"{endpoint}/files?per_page=100", paginate=True)
    desired: set[str] = set()
    for page in pages:
        for file in page:
            path = Path(file["filename"])
            if (
                path.parent != Path("changelog.d")
                or path.name in FRAGMENT_IGNORED
                or path.name.startswith(".")
                or file["status"] == "removed"
            ):
                continue
            data = github_api(
                f"repos/{head_repo}/contents/{quote(path.as_posix(), safe='/')}?ref={head_sha}"
            )
            content = base64.b64decode(data["content"]).decode("utf-8")
            # 无效碎片留给检查工作流报错，此次不改任何标签。
            try:
                desired.update(fragment_labels(path.name, content))
            except ChangelogError as error:
                print(f"碎片无效，跳过标签同步：{error}")
                return

    current = github_api(endpoint)
    if current["head"]["sha"] != head_sha or current["state"] != "open":
        print("PR 已更新或关闭，等待下一次标签同步")
        return
    existing = {label["name"] for label in current["labels"]}
    available = {
        label["name"]
        for page in github_api(f"repos/{repo}/labels?per_page=100", paginate=True)
        for label in page
    }
    for label in sorted(desired - available):
        try:
            github_api(
                f"repos/{repo}/labels",
                method="POST",
                payload={
                    "name": label,
                    "color": "c5def5",
                    "description": "按更新日志碎片自动设置",
                },
            )
        except subprocess.CalledProcessError:
            # 不同 PR 可能同时创建同名标签；确实已存在才继续，否则仍让工作流失败。
            github_api(f"repos/{repo}/labels/{quote(label, safe='')}")
    issue = f"repos/{repo}/issues/{number}/labels"
    additions = sorted(desired - existing)
    if additions:
        try:
            github_api(issue, method="POST", payload={"labels": additions})
        except subprocess.CalledProcessError as error:
            # 能不能写标签取决于仓库设置与 PR 来源，做不到时不该让整个工作流失败：
            # 标签只是给维护者看的路标，碎片本身对不对由检查工作流独立判断
            print(
                f"::warning::添加标签失败（{', '.join(additions)}）：{api_error(error)}"
            )
    for label in sorted((existing & MANAGED_LABELS) - desired):
        try:
            github_api(f"{issue}/{quote(label, safe='')}", method="DELETE")
        except subprocess.CalledProcessError as error:
            print(f"::warning::移除标签 {label} 失败：{api_error(error)}")
    print("碎片标签：" + "、".join(sorted(desired)))


if __name__ == "__main__":
    main()
