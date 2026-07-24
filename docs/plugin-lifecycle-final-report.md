# AUTO-MAS v6 插件兼容与生命周期最终纠错报告

> 日期：2026-07-23
> 工作树：`AUTO-MAS-workspace/worktrees/all-plugins-integration`
> 分支：`integration/dev-v2-dev-all-plugins`
> 范围：插件宿主、插件专项测试、wheelhouse 契约；冻结 r6 只读。

## 1. 纠错结论

上一版 GLM 报告不能作为最终完成证明，以下四项已纠正：

1. 三个新增测试此前被 `.gitignore` 的 `**/test_*.py` 吞掉，磁盘存在但无法贡献。现已为以下文件增加明确反忽略规则，`git status` 可见为未跟踪文件：
   - `tests/plugins/test_cache_store_security.py`
   - `tests/plugins/test_plugin_lifecycle_fixes.py`
   - `tests/plugins/test_verify_wheelhouse_snapshot.py`
2. `JsonPluginCache` 仍以明文 JSON 落盘。文档和 warning 只是使用限制，不是加密、访问控制或敏感字段写入阻断，不能计入“敏感配置安全完成”条件。
3. `_busy: bool` 不能阻止两个并发 reload；HTTP API 也未复用插件市场 WS 的传输层锁。现已在 manager 增加统一操作互斥，在 loader 增加 reload 互斥，并补并发测试。
4. 工作树 `plugins/wheels` 的 125-wheel 候选不是 v6 Alpha c2/r6 发布快照。`res/integration-snapshot.json` 已恢复为冻结 r6 的 127-wheel/Core 6.0.0a1 契约；工作树旧候选必须让严格校验失败，不能反向修改 marker 来制造“通过”。

## 2. 实际修复

### 2.1 并发与失败语义

- `app/plugins/manager.py`
  - 用同一个 `_operation_lock` 串行 install、uninstall、enable/disable、全局 reload、单实例 reload 和整插件 reload；因此 HTTP、旧 WS、主 WS 与开发 HMR 不会绕过彼此。
  - 新增 create/update/delete 实例事务入口；配置 `get_root → 修改 → save_root` 与 load/reload/unload 从入口到结束始终持有同一把 `_operation_lock`。
  - API update 不再先无锁落盘、返回成功后后台切换运行态；运行态现在于响应前同步完成。
  - 实例运行态应用失败时恢复操作前的完整配置根对象，并恢复旧实例运行态；配置或运行态任一回滚失败会返回“回滚不完整”及具体阶段，不再假报成功。
  - 并发 add/update/delete 与包 install/uninstall 共用进程级操作锁，两个配置 RMW 不再基于同一旧快照互相覆盖。
  - 包操作开始前等待 fast-startup 的本地 editable 安装任务结束。
  - 安装成功后若 discover、元数据解析或 entry point 归属验证失败，统一进入 `_rollback_plugin_install()`。
  - 回滚结果区分“回滚完成”与“回滚不完整，需人工清理”，不再无条件声称已回滚。
  - distribution 已卸载但 orphan 配置读取/保存失败时抛出显式部分失败，不再记录日志后返回成功。
  - orphan runtime record 会从 `loader.records` 移除，避免继续引用已删除模块。
  - 系统插件 distribution 在 manager 层拒绝卸载，不再只依赖 API 检查。
  - 清理只删除 distribution RECORD 明确列出的目标目录内文件；保留共享 namespace 中其他 distribution 的文件，并拒绝任何越界 RECORD 路径。
- `app/plugins/loader.py`
  - `_reload_lock` 串行全部实例 reload，修复两个 reload 同时操作共享 `records`、service registry 与 `_busy` 的竞态。
  - `_busy` 继续只承担 service watch 抑制，不再被误当作互斥锁。
- `app/api/plugins.py`
  - add/update/delete 只负责参数和既有响应模型转换，配置与运行态变更全部委托 manager 事务入口。
  - delete 不再直接调用 `PluginManager.loader.unload_instance()`。

### 2.2 敏感 snapshot

- `app/plugins/schema.py` 为嵌套 Pydantic 配置模型附加 `properties` 元数据。
- `app/plugins/realtime.py`
  - 根据 `sensitive=True` 递归脱敏嵌套字段。
  - schema 缺失、加载失败或出现未声明字段时 fail-closed，不广播未经分类的配置值。
  - 敏感 schema 字段的 default、examples、options 不进入前端 snapshot。
  - 脱敏始终基于深拷贝，不修改持久化或运行时原对象。

边界：插件生命周期错误字符串仍可能由第三方插件自行包含凭据；宿主不能可靠推断任意异常文本中的秘密。插件作者仍不得把 token/password 拼入异常和日志。

### 2.3 明文 cache 的准确口径

`JsonPluginCache` 当前行为保持兼容：

- 文件是明文 JSON；
- 无敏感字段声明；
- 无 DPAPI/密钥加密；
- 无运行时阻止秘密写入；
- warning 只告知调用方。

本次搜索未发现随包插件调用 `ctx.cache.register()` 或 `PluginCacheManager.register()`。因此当前随包插件没有已观察到的 cache 秘密落盘路径，但外部/本地插件仍可能误用。正式宣称“插件缓存可存敏感数据”之前，必须新增加密后端或在 API 层显式拒绝 sensitive cache。

## 3. Wheelhouse 边界

### 3.1 工作树候选（非发布权威）

路径：`plugins/wheels`

| 字段 | 实际值 |
|---|---|
| wheel 数 | 125 |
| Core | `auto-mas-core 5.4.0b1` |
| manifest SHA-256 | `336D2BBA4514230C33F52EF8F47CA1ADD95536FD59A97F3AAAD7F82AD4939074` |
| runtime-lock SHA-256 | `ABE6D2A87A69B9F67EFD77C51F298DA3AB2125275306B78E32641A30EF077A96` |

它比 c2/r6 少 `blinker 1.9.0`、`tomli-w 1.2.0`，并携带旧 Core 5.4.0b1；不能用于下一正式构建。

### 3.2 冻结 r6/c2（本轮只读参考）

路径：`_alpha_build/a1/release-nexus-a1-r6/full/resources/integration-snapshot/plugins/wheels`

| 字段 | 实际值 |
|---|---|
| wheel 数 | 127 |
| Core | `auto-mas-core 6.0.0a1` |
| 插件 distribution / entry point | 23 / 21 |
| manifest SHA-256 | `7123F7CA99A843E34C189F99744CECB568BD82A348B1457ED634438CECAD199B` |
| runtime-lock SHA-256 | `8A1CA0B31634AE2E63E55440C34C3A38998E3D20F68CA55CB6E620DA94EF3069` |

`res/integration-snapshot.json` 继续固定这套已发布契约。它不是要求把冻结 r6 直接复制到未来正式包；当前源码继续变化后，主线必须重新构建完整 wheelhouse，并以一个新 marker 原子替换 wheelhouse 与契约。

### 3.3 校验器纠错

`scripts/verify_wheelhouse_snapshot.py` 现在：

- 校验 wheel 数、插件数、entry point 数、两份 SHA-256；
- 新增校验 `core_distribution_version`，因此不再漏掉 6.0.0a1 marker 对 5.4.0b1 wheel 的冲突；
- 支持 `--wheelhouse <path>` 校验仓库外构建/冻结快照；
- 默认仍检查工作树 `plugins/wheels`，当前应返回 1。

实测：

```text
worktree_exit=1
- wheel_count 期望 127, 实际 125
- core_distribution_version 期望 6.0.0a1, 实际 5.4.0b1
- manifest_sha256 不匹配
- runtime_lock_sha256 不匹配

frozen_exit=0
[verify_wheelhouse_snapshot] 通过: wheels=127, plugins=23,
entry_points=21, core=6.0.0a1
```

## 4. 测试结果

### 4.1 纠错专项

命令：

```powershell
& 'D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\AUTO-MAS\.venv\Scripts\python.exe' -m pytest `
  tests/plugins/test_verify_wheelhouse_snapshot.py `
  tests/plugins/test_cache_store_security.py `
  tests/plugins/test_plugin_lifecycle_fixes.py `
  -q --tb=short `
  --basetemp 'D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\pytest-plugin-final-20260723-r6'
```

结果：`50 passed in 0.98s`。

### 4.2 tests/plugins 全量

首次全量不是上一报告所称的“环境 PermissionError”，而是 5 个异步测试依赖未安装的 `pytest-asyncio`。这些测试已改为 `asyncio.run` 包装，不新增运行依赖。

最终命令：

```powershell
& 'D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\AUTO-MAS\.venv\Scripts\python.exe' -m pytest `
  tests/plugins -q --tb=short `
  --basetemp 'D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\pytest-plugin-final-20260723-r5'
```

最终结果（API 事务修复前）：`134 passed in 4.33s`，0 failed、0 error、0 warning。

### 4.3 API 实例事务专项与最终插件回归

新增覆盖：

- 两个并发 update 修改不同实例时不丢写；
- add 激活失败删除已写入实例并清理运行态；
- update 加载失败恢复旧配置和旧运行态；
- delete 的 loader 吞错并写入 error record 时仍被识别为失败并回滚；
- 配置回滚失败时明确报告“回滚不完整”；
- HTTP/WS 共用端点不再直接调用 config store 或 loader；
- 既有 `code=500/status=error/message` 错误响应契约保持不变。

专项：`tests/plugins/test_plugin_lifecycle_fixes.py`，结果 `36 passed in 0.90s`。

最终 `tests/plugins` 全量结果：`142 passed in 4.37s`，0 failed、0 error、0 warning。

## 5. 证据分类

### observed

- 三个 GLM 新增测试已从 gitignore 中释放。
- install/uninstall/reload/enable 共用 manager 操作锁；loader reload 另有互斥锁。
- 安装后 discover 异常会执行回滚；回滚不完整会显式报错。
- orphan 配置保存失败会显式报部分失败。
- add/update/delete 的配置 RMW 与运行态变更现已进入同一 manager 操作锁；并发更新和完整/不完整回滚均有测试。
- API delete 已不再直接调用 loader；enabled-only update 已不再先落盘后后台执行。
- 顶层、嵌套、未知字段与敏感 schema 默认值有脱敏测试。
- `tests/plugins` 142 项全部通过。
- 工作树 125 严格校验失败；冻结 r6 127 校验通过。

### inferred

- manager 全局操作锁牺牲少量并行度，但插件包和共享 registry 是进程级资源，串行语义比并发吞吐更重要。
- 当前随包插件没有 cache 注册调用，因此明文 cache 风险尚未在随包路径触发；这不代表外部插件安全。

### unverified

- 新源码对应的最终完整 wheelhouse 尚未重建/原子导入。
- 全新 Windows 用户、无开发环境污染的离线安装尚未执行。
- HSR/M9A/MaaFW、ADB、Win32、浏览器等真实设备业务路径尚未手测。
- 第三方插件自行输出秘密到日志/异常的行为无法由宿主通用测试证明不存在。

### 跨边界阻断处理结果

此前 `app/api/plugins.py` 绕过 manager 锁的阻断已处理：add/update/delete 全部进入 manager 事务入口，enabled-only update 同步完成配置与运行态切换，delete 不再直接调用 loader。自动化已证明受管入口之间不会丢写，并能区分完整回滚与不完整回滚。

边界说明：只读的 plugins.get 不持有操作锁，运行态失败后的短暂回滚窗口内，极端并发读取可能观察到一次尝试中的配置；写端点不会基于该瞬时值提交另一个变更。若未来要求严格的线性一致读，需要为读取新增 manager snapshot 入口，本轮未改变既有 GET 性能和响应契约。

## 6. 真实环境最短手测

最终 wheelhouse 重建后按以下顺序执行：

1. 全新 Windows 用户目录首次启动，确认离线依赖安装与插件发现 23/21。
2. 快速连续触发 install/uninstall/reload/enable，确认后一个操作等待且界面无假成功。
3. 安装一个无 entry point 的测试 distribution，确认报错并且 site-packages 无幽灵 distribution。
4. 让插件 `on_start` 抛错，确认实例自动禁用、其他插件仍可启动。
5. 让 orphan 配置保存失败，确认 API 返回部分失败而非成功。
6. 查看主 WS snapshot，确认顶层和嵌套 token/password、敏感默认值均不出现。
7. 分别运行 HSR/M9A/MaaFW、ADB/Win32 控制器和 browser 插件最小业务动作。

## 7. 当前门禁结论

插件 manager/loader 与 add/update/delete API 并发、回滚自动化门禁已通过；整个正式发布门禁尚未通过，原因包括工作树仍携带 125-wheel/Core 5.4.0b1 旧候选，以及真实设备/全新 Windows 验证未完成。明文 cache 只允许非敏感数据，不得作为安全完成项。

因此当前准确结论是：**插件 manager/loader/API 写事务自动化收口完成；发布 wheelhouse 与真实环境验证仍阻断正式包。**
