# 案例：HSR 多引擎编排线

HSR 是唯一**一个 `ScriptType` 编排两个独立上游（M7A 与 SRA）**的专项，仅支持 `AutoProxy` 与 `ManualReview`，**无 `ScriptConfig.py`**。具体路径与字段现场读 `app/task/HSR/`。

## 一、核心架构约束

- **单点声明**：任务模块只在 `task_mapping.py` 的 `HSR_TASK_MODULES` 声明（`TaskMapping`、`check()`、能力快照全由此派生）。
- **四级引擎回落（每级必过 `supported_scripts` 校验）**：① 计划对象 `Managed.TaskMapping`（共享来源恒为空自动落到 ②）→ ② 托管级 `TaskMapping.<moduleKey>` → ③ `module.default_script` → ④ `effective_engines` 首个可用引擎。
- **配置来源（`Info.Base`）**：计划组（`TaskSwitch`/`Stage`/`TaskOpt`/`Managed`）由 `declare_hsr_plan_items` 单点声明；运行时用 `native_control.resolve_plan(user_config, script_config)` 区分 `plan` 与 `user_cfg`。原生来源仅 `AutoProxy` 支持、零复制直跑；**明确不支持覆写常规配置**（`Info.IfQuickConfig` 死开关不渲染）。
- **云模式（`Game.Platform = Cloud`）**：浏览器归 MAS（`tools/cloud_browser.py`，每账号独立 `data/{sid}/{uid}/cloud-profile`），自动化**恒走三月七**（SRA 不支持）。三月七连接已有浏览器 5 个硬条件：包内 `chrome.exe` + 独立 argv `--march-7th-assistant-sr-cloud-game` + 非 headless + **浏览器就绪后再写** `browser_debug_port` + `browser_type: integrated`。

## 二、高频反模式与真实事故解读（必读）

| ❌ 错误做法（反模式） | 💥 会导致什么真实事故 | ✅ 正确做法 |
| --- | --- | --- |
| 新增模块时在多处手写分支，或只配 `default_script` 没过 `supported_scripts` 校验 | 能力快照、配置项与 `check()` 立刻漂移，把某引擎不支持的模块派发过去报错 | 只改 `HSR_TASK_MODULES` 单点声明；四级回落每级必检 `supported_scripts` |
| 混用 `plan` 和 `user_cfg` 读取配置（如拿托管配置读 `Info`/`Notify`） | 共享来源下 `plan` 是 `HSRConfig`，读 `plan.Info.Name` 会把托管名错当账号名，或丢掉账号通知配置 | 读计划键（`TaskSwitch`/`Stage`/`TaskOpt`/`Managed`）传 `plan`；读 `Info`/`Data`/`Notify`/`Control` 恒传 `user_cfg` |
| 外部配置恢复时跳过 `existed=False` 条目，或新增配置文件忘加备份清单 | 任务期新写进原生目录的文件残留污染用户原生配置，甚至**永久改坏用户 M7A/SRA 配置** | 备份清单 `(label, source, backup, existed)` 中 **`existed=False` 恢复时必须删除新增路径**；逆序恢复且 `final_task`/`on_crash` 共用；同步扩展 `collect_native_files` |
| 路径锁冲突时静默阻塞等待，或收尾漏释放 | 同安装并发启动或手动更新时界面假死卡死，或后续任务永久报占用 | 冲突抛 `HSRExternalPathBusyError` 并由 API 转可读错误；`final_task` 与 `on_crash` 必须释放租约 |
| 云模式在浏览器就绪前写 `browser_debug_port`，或新增 patch 键未加白名单 | 三月七连不上已启动浏览器进而**自建共享 `UserProfile` 浏览器，破坏多账号隔离**；未进白名单的 patch 键会被 `merge_whitelist` 静默丢弃 | 严格在云浏览器就绪后再写调试端口；新键必须进 `M7A_PLATFORM_PATCH_WHITELIST`；钉 `browser_persistent_enable: False`，日志见到自建浏览器立即终止重跑并用 `cleanup_m7a_self_started_browsers` 清理 |
| 把云浏览器嵌进 Electron 窗口，或给云平台走 SRA 切号 | 三月七异常时会调 `close_all_m7a_browser()` **直接把 MAS 主进程杀掉**，且 chromedriver 版本不匹配 | 保持三月七包内独立 `chrome.exe` 进程；云平台只靠换 `cloud-profile` 切号，不注册 `StarRail.exe` 检测 |
| 在模块执行中途直接改 `Data`，或在 Vue 硬编码托管字段分支 | 模块半途失败时误记完成态导致跳过重跑；后端增字段前端还要反复改代码 | 完成态一律经 `CompletionWriteback` 写回；周期用 ISO 周 + 完成日期双字段；托管字段由后端定义动态渲染 |
| HSR native 备份池只按 SRA appdata 单指纹分桶 | 不同 M7A 安装的 `config.yaml` 会混进同一个历史池，跨实例恢复写坏别的安装 | native 池必须按 **SRA appdata 根 + M7A 安装根组合指纹**分桶（M7A 未配时才单按 SRA） |
