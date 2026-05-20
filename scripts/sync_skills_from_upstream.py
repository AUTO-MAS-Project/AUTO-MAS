#!/usr/bin/env python3
"""Sync mas-* skills from AUTO-MAS-Project/skills into ./skills/."""

from __future__ import annotations

import base64
import json
import subprocess
import urllib.request
from pathlib import Path

REPO = "AUTO-MAS-Project/skills"
BRANCH = "main"
ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
def gh_api(path: str) -> bytes:
    out = subprocess.check_output(
        ["gh", "api", f"repos/{REPO}/{path}", "-q", ".content"],
        text=True,
    )
    return base64.b64decode(out.replace("\n", ""))


def gh_tree() -> list[dict]:
    url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.load(resp)
    return [n for n in data["tree"] if n["type"] == "blob"]


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("---", 3)
    if end == -1:
        return text
    return text[end + 3 :].lstrip("\n")


def main() -> None:
    blobs = gh_tree()
    paths = [n["path"] for n in blobs if n["path"].startswith("mas-")]

    for rel in paths:
        parts = Path(rel).parts
        if len(parts) < 2:
            continue
        skill_name = parts[0]

        dest = SKILLS_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = gh_api(f"contents/{rel}").decode("utf-8")

        if rel.endswith("/SKILL.md"):
            guide = SKILLS_DIR / skill_name / "references" / "guide.md"
            guide.parent.mkdir(parents=True, exist_ok=True)
            header = (
                f"# {skill_name}（完整说明）\n\n"
                f"对应 Skill：`{skill_name}`。来源：{REPO}。\n\n---\n\n"
            )
            guide.write_text(header + strip_frontmatter(content), encoding="utf-8")
            print(f"updated {guide.relative_to(ROOT)}")
        else:
            dest.write_text(content, encoding="utf-8")
            print(f"updated {dest.relative_to(ROOT)}")

    print("done (SKILL.md summaries in repo are not overwritten)")


if __name__ == "__main__":
    main()
