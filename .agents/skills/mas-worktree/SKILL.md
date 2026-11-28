---
name: mas-worktree
description: Use before an AI creates or starts using an AUTO-MAS worktree, runs Python checks or tests there, prepares dependencies, or investigates a duplicate .venv. Verify existing development environments before any dependency download, reuse compatible environments, and only clean up a confirmed duplicate.
---

# AUTO-MAS worktree：先查，再复用

## 开工前（只读，不下载）

1. 用 `git worktree list --porcelain` 确认当前检出，以及其他工作树和主检出的位置。新建 worktree 只检出源码，不挂接依赖下载；若宿主已创建 worktree，直接从环境检查开始。
2. 在使用的同一台电脑、同一终端检查 `AUTO_MAS_DEV_ENV_ROOT`、`UV_PROJECT_ENVIRONMENT`、`VIRTUAL_ENV` 和 `git config --local --get automas.backendAppRoot`。Windows 上进程变量为空时，继续用 `[Environment]::GetEnvironmentVariable('AUTO_MAS_DEV_ENV_ROOT', 'User')` 和 `'Machine'` 检查已登记值；不要将“当前 shell 没继承”当作“没有环境”。有多个来源不一致就先确认，必要时仅在本次 shell 导入已确认的值，不改用户或系统设置。后两个环境变量只是排查线索，不能证明它是共享池。
3. 按用途检查实际环境，不只看变量是否存在：
   - 只改文档、读代码或做不需要项目依赖的检查：不要建环境。
   - Python 测试：运行 `pwsh -NoProfile -File ./scripts/dev-backend.ps1 Check -Target Test`；通过后走同一入口的 `Test`，或直接用它报告的解释器执行其它检查。
   - Windows 桌面联调：运行 `pwsh -NoProfile -File ./scripts/dev-backend.ps1 Check`；只认包含标记的专用测试包，不指向日常安装。确需启动再用 `Start`。两种入口不互相替代。
4. `Check` 失败先定位：没有继承变量、工具不在 PATH、环境根路径错、缺少对应锁文件的池、Python 或依赖版本不匹配是不同问题。没有确认环境前不得运行 `uv sync`、普通 `uv run`、`uv venv`、项目依赖安装或启动会自动装依赖的任务。没有合格环境时，可以继续不依赖它的工作；确有必要再请用户确认共享池路径与一次性准备，按[开发后端文档](../../../docs/developer-backend.md#精简-worktree可选)只建匹配的新池，不在 worktree 建 `.venv` 或覆盖旧池。

## AI 跳过检查并下载后的兜底

1. 停止本次下载或运行，并记录命令、当前 worktree 根、确切写入路径及来源。没有创建前后证据时，不把已有 `.venv` 当作本次产物。若命令只填了 uv 缓存而没建虚拟环境，不清缓存。
2. 先用 `Check -Target Test` 和一项必要测试验证要保留的共享环境；运行前关闭本次 AI 的测试子进程，清除指向候选目录的本次会话激活状态。比较 Python 版本、平台、架构、当前锁文件和实际锁定依赖；本次未完成装载的副本，只有记录能证明它是同一工作树用同一份锁创建的中断产物，才算候选。不要为了比较而执行来源不明的解释器。
3. 只把**本次 AI 新建的、当前 worktree 直接子目录 `.venv`**列为可清理项。用 `git check-ignore`、`git ls-files` 和文件系统实际路径确认候选未入库且不包含受版本控制内容，不是符号链接、目录联接或其他重解析点（目录树内有此类项也不自动处理），不被任何运行、设置或其他 worktree 使用，且与专用安装包、共享池、另外的 worktree 均不重叠。不能证明任何一项，就只报告，等人确认；不得删除主检出、历史环境、安装包、插件目录或 uv 缓存。
4. 先告知确切路径、保留的解释器和清理依据。验证全通过时，只处理该单个重复目录：优先移到可还原的隔离目录，再用共享解释器复验；无可恢复方式时，永久删除前让用户确认精确路径。不要使用通配符、全盘搜索删除或强制终止别的进程。复验失败就恢复，不继续清理。

交付时写清楚：命中哪个现有环境、是否下载、是否有重复项、实际清理了什么；没有执行的不能说做了。
