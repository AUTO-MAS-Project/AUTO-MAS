# 从上游同步 Skills

官方 Skill 仓库：<https://github.com/AUTO-MAS-Project/skills>

## 一键同步（需 `gh` 已登录且可访问 GitHub）

在仓库根目录执行：

```powershell
python scripts/sync_skills_from_upstream.py
```

脚本会：

1. 通过 `gh api` 拉取上游各 `mas-*/SKILL.md` 写入 `skills/<name>/references/guide.md`
2. 拉取 `mas-code-standards/references/style-observations.md` 与各 `agents/openai.yaml`
3. **不会**覆盖本仓库已手工精简的 `SKILL.md` 摘要

同步后请人工检查：摘要 `SKILL.md` 是否与 `guide.md` 一致，必要时更新摘要条目。

## 手工同步

1. 对比上游仓库目录树。
2. 更新 `references/guide.md` 与 `references/*.md`。
3. 视上游变更修订对应 `SKILL.md` 摘要与 `description` frontmatter。
