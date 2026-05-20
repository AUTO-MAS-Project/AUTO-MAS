# 从上游同步 Skills

官方 Skill 仓库：<https://github.com/AUTO-MAS-Project/skills>

本仓库 `skills/mas-*` 与上游对应，但采用 **根目录 `SKILL.md` 摘要** + **`references/guide.md` 全文** 的双层结构；同步时**不要覆盖**各 Skill 根目录的 `SKILL.md`。

## 用 Git 同步（推荐）

在 AUTO-MAS 仓库根目录执行。

### 1. 添加上游 remote（仅首次）

```powershell
git remote add skills-upstream https://github.com/AUTO-MAS-Project/skills.git
```

若已存在可跳过，或执行 `git remote -v` 确认。

### 2. 拉取上游

```powershell
git fetch skills-upstream main
```

### 3. 对照并合并文件

浅克隆到临时目录便于对比（也可在 GitHub 网页 diff）：

```powershell
git clone --depth 1 --branch main https://github.com/AUTO-MAS-Project/skills.git .tmp/skills-upstream
```

对每个 `mas-*` Skill：

| 上游路径 | 本仓库路径 |
|----------|------------|
| `mas-*/references/**` | `skills/mas-*/references/**`（原样覆盖或按需合并） |
| `mas-*/agents/**` | `skills/mas-*/agents/**` |
| `mas-*/SKILL.md` | 将正文（去掉 `---` 包裹的 YAML frontmatter）写入 `skills/mas-*/references/guide.md`，保留 guide 页头说明来源 |

**勿覆盖** `skills/mas-*/SKILL.md`（本仓库摘要）。

完成后删除临时目录：

```powershell
Remove-Item -Recurse -Force .tmp/skills-upstream
```

### 4. 提交前检查

- [ ] 各 `references/guide.md` 已与上游 `SKILL.md` 对齐
- [ ] 根目录 `SKILL.md` 摘要仍准确；上游有大改时手工更新 `description` 与条目
- [ ] `skills/README.md` 表格无需改时可不动

## 仅本仓库专有的 Skill

`mas-script-specialized-adapter` 等仅存在于本仓库的 Skill，不在上游 `mas-*` 列表中，按 [README.md](./README.md) 在本仓维护，不参与上述同步。
