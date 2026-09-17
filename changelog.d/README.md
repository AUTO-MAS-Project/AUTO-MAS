# 更新日志碎片

每个 PR 在这个目录下放**一个**文件，写一句给用户看的话。发版时脚本把它们编译进
`CHANGELOG.md` 的新版本段并删掉，所以平时不要改 `CHANGELOG.md`、`res/version.json`
和任何版本号，它们只由发版 PR 更新。

## 怎么写

```powershell
python scripts/changelog.py add fix maa "修复理智不足时剿灭被误记为本周已完成的问题"
# → changelog.d/<当前分支名>.fix.md，内容：
#   project: maa
#   修复理智不足时剿灭被误记为本周已完成的问题
```

也可以手动新建文件：

- 文件名 `<PR 号或分支名>.<分类>.md`，例如 `683.feat.md`、`mumu-force-kill.fix.md`。
- 首行 `project: <项目键>`，键从下面的项目表里选；本体其他部分写 `core`。
- 正文一行、**不超过 50 字**，只写做了什么，不用 `- ` 开头，不写项目名、PR 号和署名——
  这三样发版时按碎片和它的合并提交自动补成 `(项目) 做了什么 (#PR) by @作者`。
- 替别人提交时可以再加一行 `author: 登录名` 覆盖自动署名。
- 维护者觉得这条值得放进「本次亮点」，就再加一行 `highlight: true`（合并前在 PR 里加，或合并后
  直接改 dev 上的碎片）；编译时这条进「本次亮点」而不是原分类。只加减这一行不算改别人的碎片。
- 不要重命名或改写别人的碎片：署名按最近一次新增该文件的提交算，重命名会把署名转给重命名的人；
  文件名要改请让作者自己改，或在碎片里写明 `author:`。

| 后缀 | 编译后的分类 | 用途 |
| --- | --- | --- |
| `breaking` | 破坏性变更 | 需要用户动手确认，或会改变既有行为 |
| `feat` | 新增 | 新功能 |
| `change` | 变更 | 对现有功能的调整与优化；拿不准时宁可写 change 不要写 fix |
| `remove` | 移除 | 已经移除，或不再建议使用、即将移除 |
| `fix` | 修复 | bug 修复 |
| `security` | 安全 | 安全性改进 |
| `dev` | 开发流程 | 只影响贡献者、用户看不见；不进公告 |

项目键（公告里同一分类内按这个顺序排，本体排最后）：

| 键 | 公告里显示 | 键 | 公告里显示 |
| --- | --- | --- | --- |
| `maa` | MAA | `mfw` | MFW |
| `maaend` | MaaEnd | `general` | 通用脚本 |
| `m9a` | M9A | `home` | 首页 |
| `hsr` | HSR | `scheduler` | 调度 |
| `bettergi` | BetterGI | `emulator` | 模拟器 |
| `zzz` | 绝区零一条龙 | `display` | 虚拟显示器 |
| `okww` | ok-ww | `notify` | 通知 |
| `oknte` | ok-nte | `update` | 更新 |
| `baah` | BAAH | `backup` | 配置备份 |
| `src` | SRC | `core` | （本体其他，不加前缀） |

表在 `scripts/changelog.py` 的 `PROJECTS` 里，新专项加一行即可。一条改动横跨几个项目时选最主要的那个。

## 写作要求

- **面向用户**：只描述用户可观察到的改动或修复，删掉实现细节、类型名、接口路径、状态码。
- **写症状，不写根因**：写「修复了什么现象」，不写「为什么、怎么改的」。
- **一条 PR 一句话**：把全部改动概括成一句，不要拆成多条；50 字写不下就是该删细节了。
- 纯文档、CI、测试或用户不可见的重构不需要碎片，给 PR 打 `skip-changelog` 标签。

## CI 会检查什么

- 改了 `app/`、`frontend/src/`、`frontend/electron/` 或 `main.py` 的 PR 必须恰好新增一个碎片。
- 碎片必须有 `project:` 且键在项目表里，正文不超过 50 字。
- 「本次亮点」没有后缀，只能由 `highlight: true` 标出来。
- 普通 PR 不得改 `CHANGELOG.md`、`res/version.json`，也不得改动 `pyproject.toml`、
  `frontend/package.json`、`app/core/config.py`、`uv.lock` 里的版本号。
- 不要修改或删除别人的碎片。
- 维护者整理历史更新日志时给 PR 打 `changelog-maintenance` 标签，上述限制放开。

## 发版时发生什么

维护者在 Actions 里运行「准备发版」，选 `beta` / `stable` / `patch`：脚本按最新 tag 推出
版本号（公测 N+1；转正与最后一个 beta 同号；补丁 Z+1），把碎片编译成 `## [vX.Y.Z] - 日期`
段放到 `CHANGELOG.md` 顶部，删除碎片，写入五处版本号，开出 `Release vX.Y.Z` PR。
转正时同号的全部 beta 段会合并成一个正式版段，稳定通道的用户看到的就是整个周期的汇总。

Release 正文首行是给客户端更新提示用的 JSON，Mirror 酱只保留前 20000 字符。脚本给首行
18000 字符的预算：超预算时从最老的版本段开始丢；本版段自己就超预算的话，
发版 PR 的检查会红，合并前要在 PR 里直接改 `CHANGELOG.md` 新版本段精简或合并条目，
改完运行 `python scripts/changelog.py sync` 一起提交，检查才会绿。
