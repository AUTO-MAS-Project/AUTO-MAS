# 更新日志碎片

每个 PR 在这个目录下放**一个**文件，写一句给用户看的话。发版时脚本把它们编译进
`CHANGELOG.md` 的新版本段并删掉，所以平时不要改 `CHANGELOG.md`、`res/version.json`
和任何版本号，它们只由发版 PR 更新。

## 怎么写

```powershell
python scripts/changelog.py add fix "MAA专项 修复理智不足时剿灭被误记为本周已完成的问题"
# → changelog.d/<当前分支名>.fix.md
```

也可以手动新建文件：

- 文件名 `<PR 号或分支名>.<分类>.md`，例如 `683.feat.md`、`mumu-force-kill.fix.md`。
- 内容就是那一句话，一行，不用 `- ` 开头，不写署名。署名在发版时按这个文件的提交作者自动补。
- 替别人提交时可以在第一行写 `author: 登录名` 覆盖自动署名。
- 不要重命名或改写别人的碎片：署名按最近一次新增该文件的提交算，重命名会把署名转给重命名的人；
  文件名要改请让作者自己改，或在碎片里写明 `author:`。

| 后缀 | 编译后的分类 | 用途 |
| --- | --- | --- |
| `breaking` | 破坏性变更 | 需要用户动手确认，或会改变既有行为 |
| `feat` | 新增 | 新功能 |
| `change` | 变更 | 对现有功能的调整与优化；拿不准时宁可写 change 不要写 fix |
| `deprecate` | 弃用 | 不再建议使用、即将移除 |
| `remove` | 移除 | 已经移除 |
| `fix` | 修复 | bug 修复 |
| `security` | 安全 | 安全性改进 |
| `dev` | 开发流程 | 只影响贡献者、用户看不见 |

## 写作要求

- **面向用户**：只描述用户可观察到的改动或修复，删掉实现细节、类型名、接口路径、状态码。
- **写症状，不写根因**：写「修复了什么现象」，不写「为什么、怎么改的」。
- **一条 PR 一句话**：把全部改动概括成一句，不要拆成多条。
- 纯文档、CI、测试或用户不可见的重构不需要碎片，给 PR 打 `skip-changelog` 标签。

## CI 会检查什么

- 改了 `app/`、`frontend/src/`、`frontend/electron/` 或 `main.py` 的 PR 必须恰好新增一个碎片。
- 普通 PR 不得改 `CHANGELOG.md`、`res/version.json`，也不得改动 `pyproject.toml`、
  `frontend/package.json`、`app/core/config.py`、`uv.lock` 里的版本号。
- 不要修改或删除别人的碎片。
- 维护者整理历史更新日志时给 PR 打 `changelog-maintenance` 标签，上述限制放开。

## 发版时发生什么

维护者在 Actions 里运行「准备发版」，选 `beta` / `stable` / `patch`：脚本按最新 tag 推出
版本号（公测 N+1；转正与最后一个 beta 同号；补丁 Z+1），把碎片编译成 `## [vX.Y.Z] - 日期`
段放到 `CHANGELOG.md` 顶部，删除碎片，写入五处版本号，开出 `Release vX.Y.Z` PR。
转正时同号的全部 beta 段会合并成一个正式版段，稳定通道的用户看到的就是整个周期的汇总。
