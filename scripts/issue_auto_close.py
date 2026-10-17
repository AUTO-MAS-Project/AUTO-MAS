#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

"""给误勾选留 10 分钟纠正时间，关闭提交满 24 小时仍缺日志的 Bug。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

UNREAD_GRACE = timedelta(minutes=10)
LOG_GRACE = timedelta(hours=24)
# 工作流推到 dev 时就登记，同步到 main 才生效；巡检只补登记最近一天新建的反馈。
CATCH_UP = timedelta(hours=24)
STATE_PREFIX = "<!-- auto-mas-issue-policy:v1 "
STATE_REGEX = re.compile(re.escape(STATE_PREFIX) + r"(\{[^\n]+\}) -->")
UNREAD_TEXT = "我未仔细阅读这些内容，只是一键已读所有内容，并相信这不会影响问题的处理"
ARCHIVE_SUFFIXES = (".zip", ".7z", ".rar", ".gz", ".log", ".txt")
LOG_LINE = re.compile(
    r"(?im)^\s*(?:\[)?(?:\d{4}[-/]\d{2}[-/]\d{2}[ T]|\d{2}[-/]\d{2}\s+)?"
    r"\d{2}:\d{2}:\d{2}[^\n]*\b"
    r"(?:TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|SUCCESS|TRC|DBG|INF|WRN|ERR|FTL)\b"
)


def github_api(
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    paginate: bool = False,
) -> Any:
    """沿用 runner 的 gh，Issue 内容只作为数据，不经过 shell。"""

    command = ["gh", "api", "--method", method, endpoint]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def unread_checked(body: str) -> bool:
    """只检查模板的提问前声明，描述中的引用不触发。"""

    section = re.match(
        r"(?ms)\A\s*### 在提问之前(?:\.{3}|…)[ \t]*\r?\n(.*?)(?=^### |\Z)",
        body,
    )
    if section is None:
        return False
    return (
        re.search(
            r"(?im)^- \[x\][ \t]+" + re.escape(UNREAD_TEXT) + r"[ \t]*\r?$",
            section[1],
        )
        is not None
    )


def has_logs(text: str) -> bool:
    """认可日志附件、带时间与级别的日志片段，或完整异常堆栈。"""

    for url in re.findall(r'https?://[^\s<>"\)\]]+', text):
        parsed = urlsplit(url)
        path = unquote(parsed.path).lower()
        upload = parsed.hostname == "github.com" and re.search(
            r"^/(?:user-attachments/files|[^/]+/[^/]+/files)/", path
        )
        # Release 安装包、源码 ZIP 不算日志；外链需要文件名说明是日志。
        named_logs = re.search(r"(?i)logs?|日志", path.rsplit("/", 1)[-1])
        if path.endswith(ARCHIVE_SUFFIXES) and (
            upload or named_logs or path.endswith(".log")
        ):
            return True
    # GitHub 的 assets 链接可能不带扩展名，上传文件名仍保留在链接标题中。
    if re.search(
        r"(?i)(?<!!)\[[^\]\n]+\.(?:zip|7z|rar|gz|log|txt)\]"
        r"\(https://github\.com/user-attachments/(?:files|assets)/[^\s)]+\)",
        text,
    ):
        return True
    if LOG_LINE.search(text):
        return True
    python_traceback = (
        "Traceback (most recent call last):" in text
        and re.search(r'(?m)^\s*File "[^"]+", line \d+', text) is not None
        and re.search(r"(?m)^[\w.]*(?:Error|Exception):\s*\S", text) is not None
    )
    # Electron/脚本日志也可能只留下 JS 或 .NET 异常堆栈，没有时间前缀。
    stack_trace = (
        re.search(r"(?m)^[\w.]*(?:Error|Exception):\s*\S", text) is not None
        and len(re.findall(r"(?m)^\s+at\s+\S[^\n]*(?::\d+|\([^\n]*\))", text)) >= 2
    )
    return python_traceback or stack_trace


def read_state(comments: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict]:
    for comment in comments:
        # 提交者复制 HTML 标记不能伪造机器人计时。
        if (
            comment["user"]["login"] != "github-actions[bot]"
            or comment["user"]["type"] != "Bot"
        ):
            continue
        matched = STATE_REGEX.search(comment.get("body") or "")
        if matched:
            state = json.loads(matched[1])
            for key in (
                "unread_since",
                "logs_deadline",
                "registered_at",
                "reopened_at",
            ):
                if state.get(key):
                    parse_time(state[key])
            return comment, state
    return None, {"unread_since": None, "logs_deadline": None}


def issue_has_logs(issue: dict, comments: list[dict]) -> bool:
    return has_logs(issue.get("body") or "") or any(
        has_logs(comment.get("body") or "")
        for comment in comments
        if not (
            comment["user"]["login"] == "github-actions[bot]"
            and (comment.get("body") or "").startswith(STATE_PREFIX)
        )
    )


def is_bug(issue: dict) -> bool:
    return any(label["name"].lower() == "bug" for label in issue["labels"])


def close_reason(issue: dict, comments: list[dict], state: dict, now: datetime) -> str:
    if issue["state"] != "open" or "pull_request" in issue:
        return ""
    if any(label["name"] == "skip-auto-close" for label in issue["labels"]):
        return ""
    if unread_checked(issue.get("body") or "") and state.get("unread_since"):
        # 活动时间作保守下限：排队期间取消再勾上，即使事件被合并也重新给足 10 分钟。
        since = max(parse_time(state["unread_since"]), parse_time(issue["updated_at"]))
        if now >= since + UNREAD_GRACE:
            return "unread"
    if (
        is_bug(issue)
        and state.get("logs_deadline")
        and now >= parse_time(state["logs_deadline"])
        and not issue_has_logs(issue, comments)
    ):
        return "logs"
    return ""


def reminder_body(state: dict, *, logs_present: bool, bug: bool) -> str:
    lines = []
    if state.get("unread_since"):
        lines.append(
            "你勾选了「我未仔细阅读」。请重新阅读声明；如果是误点，请取消勾选。"
            "保留勾选且至少 10 分钟没有新操作后，此 Issue 会自动关闭。"
        )
    if bug and state.get("logs_deadline"):
        if logs_present:
            lines.append("已识别到日志附件或日志片段，不会因缺少日志自动关闭。")
        else:
            lines.append(
                f"请在 {state['logs_deadline']}（UTC）之前，"
                "在正文或评论中补充日志附件或粘贴日志片段，逾期仍无日志会自动关闭。"
                "截图或仅声明「已上传日志」不算日志。"
            )
    if not lines:
        lines.append("反馈检查已通过。")
    marker = STATE_PREFIX + json.dumps(state, separators=(",", ":")) + " -->"
    return marker + "\n\n" + "\n\n".join(lines)


def process_issue(
    repo: str,
    number: int,
    *,
    event: dict,
    policy_started_at: datetime,
    include_history: bool = False,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    endpoint = f"repos/{repo}/issues/{number}"
    issue = github_api(endpoint)
    if issue["state"] != "open" or "pull_request" in issue:
        return
    if any(label["name"] == "skip-auto-close" for label in issue["labels"]):
        return
    comments = [
        comment
        for page in github_api(f"{endpoint}/comments?per_page=100", paginate=True)
        for comment in page
    ]
    reminder, state = read_state(comments)
    checked = unread_checked(issue.get("body") or "")
    bug = is_bug(issue)
    action = (
        event.get("action") if event.get("issue", {}).get("number") == number else None
    )
    newly_labeled = (
        action == "labeled" and event.get("label", {}).get("name", "").lower() == "bug"
    )
    new_issue = parse_time(issue["created_at"]) >= max(
        policy_started_at, now - CATCH_UP
    )
    previous_body = event.get("changes", {}).get("body", {}).get("from")
    newly_checked = (
        checked and previous_body is not None and not unread_checked(previous_body)
    )
    enroll = new_issue or newly_labeled or include_history
    # 巡检补回丢失的 opened 事件，历史 Issue 只在新操作或手动启用时登记。
    if reminder is None and not enroll and not newly_checked:
        return
    if reminder is None and not bug and not checked:
        return
    if reminder is None:
        state["registered_at"] = timestamp(now)
        if checked and not (new_issue or newly_checked or include_history):
            # 补打 bug 标签登记的旧 Issue，早就勾上的「未仔细阅读」不追溯计时。
            state["unread_ignored"] = True
    if bug and not state.get("logs_deadline") and enroll:
        # 从登记时起算，补登记或迟到的标签不会让期限一出现就已过期。
        state["logs_deadline"] = timestamp(now + LOG_GRACE)
    if (
        reminder is None
        or action == "reopened"
        or close_reason(issue, comments, state, now)
    ):
        # 巡检可能排在 reopened 事件之前；从时间线恢复重开时间，不靠事件执行顺序。
        reopened = [
            parse_time(item["created_at"])
            for page in github_api(f"{endpoint}/timeline?per_page=100", paginate=True)
            for item in page
            if item.get("event") == "reopened"
        ]
        latest = max(reopened, default=None)
        handled = parse_time(
            state.get("reopened_at")
            or (issue["created_at"] if reminder is None else state["registered_at"])
        )
        if latest is not None and latest > handled:
            state["reopened_at"] = timestamp(latest)
            state["unread_since"] = None
            if state.get("logs_deadline"):
                state["logs_deadline"] = timestamp(
                    max(parse_time(state["logs_deadline"]), latest + LOG_GRACE)
                )
    if newly_checked:
        state.pop("unread_ignored", None)
    if checked and not state.get("unread_ignored"):
        if not state.get("unread_since") or newly_checked:
            state["unread_since"] = timestamp(now)
    else:
        state["unread_since"] = None
        if not checked:
            # 取消勾选后解除豁免，之后再勾选按新的误勾选计时。
            state.pop("unread_ignored", None)
    body = reminder_body(state, logs_present=issue_has_logs(issue, comments), bug=bug)
    if reminder is None:
        github_api(f"{endpoint}/comments", method="POST", payload={"body": body})
        print(f"#{number}：已登记提醒")
        return
    if reminder["body"] != body:
        github_api(
            f"repos/{repo}/issues/comments/{reminder['id']}",
            method="PATCH",
            payload={"body": body},
        )
        # 写提醒也会改变活动时间，下一轮再判断关闭。
        return
    if not close_reason(issue, comments, state, now):
        return

    # 排队或 API 调用期间可能补日志、取消勾选或由维护者接管，关闭前再取一次最新数据。
    comments = [
        comment
        for page in github_api(f"{endpoint}/comments?per_page=100", paginate=True)
        for comment in page
    ]
    current = github_api(endpoint)
    if current["updated_at"] != issue["updated_at"] or current.get("body") != issue.get(
        "body"
    ):
        print(f"#{number}：已有新操作，留到下一轮检查")
        return
    reason = close_reason(current, comments, state, now)
    if not reason:
        return
    explanation = {
        "unread": "「我未仔细阅读」仍处于勾选状态，10 分钟纠正期已过，自动关闭。",
        "logs": "补充日志的 24 小时期限已过，正文与评论中仍未找到日志，自动关闭。",
    }[reason]
    github_api(
        endpoint,
        method="PATCH",
        payload={"state": "closed", "state_reason": "not_planned"},
    )
    github_api(
        f"{endpoint}/comments",
        method="POST",
        payload={
            "body": explanation + "\n\n更正勾选或补充日志后，可以重新打开此 Issue。"
        },
    )
    print(f"#{number}：已关闭（{reason}）")


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    include_history = os.environ.get("INCLUDE_HISTORY", "false").lower() == "true"
    workflow = github_api(f"repos/{repo}/actions/workflows/issue-auto-close.yml")
    policy_started_at = parse_time(workflow["created_at"])
    if event.get("issue"):
        numbers = [event["issue"]["number"]]
    else:
        numbers = [
            issue["number"]
            for page in github_api(
                f"repos/{repo}/issues?state=open&per_page=100", paginate=True
            )
            for issue in page
            if "pull_request" not in issue
        ]
    failed = []
    for number in numbers:
        try:
            process_issue(
                repo,
                number,
                event=event,
                policy_started_at=policy_started_at,
                include_history=include_history,
            )
        except (subprocess.CalledProcessError, ValueError) as error:
            # 一个 Issue 的权限/网络错误不阻断其余反馈，但最后仍让 CI 报失败。
            detail = (
                error.stderr
                if isinstance(error, subprocess.CalledProcessError)
                else str(error)
            )
            print(f"::error::#{number} 检查失败：{detail}")
            failed.append(number)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
