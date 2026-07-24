# AUTO-MAS v6 模拟器管理 — API / Provider / Fallback 契约

> Subagent A 产出。基于 `integration/dev-v2-dev-all-plugins` 工作树源码（HEAD `b5e872815`）。
> 所有结论标记：`observed`（源码确认）/ `inferred`（推断）/ `proposed`（修复建议）/ `unverified`。

---

## 1. 调用链总览

### 1.1 配置 CRUD 调用链

```
HTTP /api/emulator/{get,add,update,delete,order}
  └─ app/api/emulator.py                  # 传输映射：解析 *In，调用 service，返回 *Out
      └─ app/plugins/emulator_compat.py   # get_emulator_service() 选择 provider 或 fallback
          ├─ [provider 启用时] PluginManager.service.get("emulator")  # 插件提供的服务实例
          └─ [无 provider 时]   LegacyEmulatorService                  # host fallback
              └─ app/core/config.py       # Config.get_emulator / add_emulator / update_emulator /
                                          # del_emulator / reorder_emulator
                  └─ Config.EmulatorConfig (MultipleConfig[EmulatorConfig])
                      └─ app/models/config.py: EmulatorConfig(ConfigBase)
```

`observed`：配置 CRUD 全部经 `Config.EmulatorConfig`（`MultipleConfig`），UUID 由 `ConfigBase` 生成与索引；`del_emulator` 会级联清理 MAA/SRC/MaaEnd/General 脚本中引用该模拟器的字段（`Config.del_emulator` 行 2191-2299）。

### 1.2 操作（open/close/show）调用链

```
HTTP POST /api/emulator/operate  (EmulatorOperateIn)
  └─ app/api/emulator.py: operation_emulator
      └─ service.operate(operate, emulatorId, index)
          ├─ [provider] plugin service.operate(...)
          └─ [fallback] LegacyEmulatorService.operate
              └─ app/core/emulator_manager.py: EmulatorManager.operate_emulator
                  └─ (修复前) asyncio.create_task(operate_emulator_task(...))  # fire-and-forget
                      └─ operate_emulator_task
                          ├─ get_emulator_instance(emulator_id)  # 加载配置 + 广告屏蔽副作用
                          │   └─ EMULATOR_TYPE_BOOK[type](config)  # MumuManager / LDManager / GeneralDeviceManager
                          ├─ temp_emulator.open/close/setVisible(index)
                          └─ [失败] Publisher.send(EMULATOR_NOTICE, WSTaskNoticeData(level=error))
```

`observed`（假成功问题）：
- `emulator_manager.py:85-89`：`operate_emulator` 用 `asyncio.create_task(...)` 立即返回，不 await。
- `emulator_compat.py:44-47`：`LegacyEmulatorService.operate` await `EmulatorManager.operate_emulator(...)`，但后者不返回结果也不抛异常。
- `api/emulator.py:160-169`：`operation_emulator` await `service.operate(...)` 后立即返回 `OutBase()`（`code=200, status="success"`）。
- 真实失败仅通过 WS `emulator.notice` 推送；HTTP 已先返回成功 → **假成功**。

### 1.3 状态查询调用链

```
HTTP POST /api/emulator/status  (EmulatorGetIn)
  └─ app/api/emulator.py: get_status
      └─ service.status(emulatorId)
          └─ EmulatorManager.get_status(emulator_id)
              └─ for eid in emulator_range:
                    get_emulator_instance(eid)   # 任一损坏即抛异常
                    temp_emulator.getInfo(None)  # 转换为 SchemaDeviceInfo
```

`observed`（无隔离问题）：`emulator_manager.py:116-141` 循环中对每个 `emulator_id` 调用 `get_emulator_instance`（UUID 非法 / 类型不支持 / 路径失效即抛）与 `getInfo`（进程失败即抛）。单个损坏配置中断整列。

### 1.4 搜索调用链

```
HTTP POST /api/emulator/emulator/search
  └─ app/api/emulator.py: search_emulators
      └─ service.search_installed()
          └─ LegacyEmulatorService.search_installed
              └─ asyncio.to_thread(search_all_emulators)  # app/utils/emulator/tools.py
                  └─ _collect_uninstall_paths_by_emulator_type  # 枚举注册表卸载表
```

`observed`：搜索仅读注册表卸载表 `UninstallString`，去重（大小写不敏感路径 key），按 `EMULATOR_PATH_BOOK` 顺序稳定输出，仅返回 `is_file()` 命中的主管理器 exe，不导入不存在路径。

### 1.5 WS 通知链

```
EmulatorManager.operate_emulator_task (失败)
  └─ Publisher.send(id=ID_EMULATOR_MANAGER, type=EMULATOR_NOTICE, data=WSTaskNoticeData)
      └─ app/core/ws/publisher.py: WSPublisher.send
          └─ ws_manager.send_json(build_message(...))  # 主 WS 连接
```

`observed`：`Publisher` 为单例 `ws_publisher`（`publisher.py:264`）。`send` 返回 `bool`（连接是否就绪）。`EMULATOR_NOTICE = "emulator.notice"` 不在 `MERGEABLE_TYPES` 中，故不进入快照缓存，仅实时推送。

### 1.6 下拉框调用链

```
Config.get_emulator_combox()         # 列出所有模拟器名/UUID
Config.get_emulator_devices_combox() # 列出某模拟器的多开实例（调用 EmulatorManager.get_emulator_instance）
```

`observed`：`get_emulator_devices_combox`（`config.py:3007-3029`）对 `general` 类型返回空（不支持扫描多开）；其他类型调用 `EmulatorManager.get_emulator_instance` → `getInfo`。

---

## 2. Provider / Fallback 切换规则

### 2.1 服务注册架构

```
app/plugins/service_registry.py: ServiceRegistry
  ├─ provide(name, owner)   # 声明服务槽（不写值）
  ├─ set(name, value, owner) # 写入服务值 + 发布变更
  ├─ get(name, default)      # 多提供者时按 owner 字典序返回首个
  ├─ drop(owner)             # 移除某 owner 的所有服务值
  └─ owners(name)            # 返回声明该服务的 owner 集合
```

`observed`：
- `EMULATOR_SERVICE_NAME = "emulator"`（`loader.py:40`）。
- `HOST_EMULATOR_COMPAT_OWNER = "host:legacy-emulator"`（`loader.py:39`）。

### 2.2 切换规则（`app/plugins/loader.py`）

| 场景 | 行为 | 代码位置 |
|------|------|----------|
| 无 plugin 提供 emulator | `_register_host_emulator_compat`：`service.set("emulator", LegacyEmulatorService(), "host:legacy-emulator")` | `loader.py:126-140` |
| plugin 成功加载且 provides 含 emulator | `_drop_host_emulator_compat`：`service.drop(HOST_EMULATOR_COMPAT_OWNER)` | `loader.py:142-145`, `1086-1091` |
| plugin 缺失 required 服务（加载失败） | `_restore_host_emulator_compat_after_provider_failure`：若 `emulator` 未 ready 则重新注册 host fallback | `loader.py:147-157`, `1080-1084` |
| plugin 卸载（on_unload） | `service.drop(record.instance_id)`；若 `emulator` 未 ready 且非 busy 则重新注册 host fallback | `loader.py:1299-1307` |
| 启动期批量配置 | `_configure_host_compat_services`：先 drop host，若无真实 provider 再 register host | `loader.py:159-174` |

`observed`：
- **非共存保证**：host fallback 仅在 `owners("emulator")` 为空时注册；plugin 加载成功后立即 drop host owner。
- **恢复保证**：plugin 失败/卸载后，若 `emulator` 未 ready，重新注册 host fallback。
- `get_emulator_service()`（`emulator_compat.py:97-106`）是 API 层的惰性选择器：优先 `PluginManager.service.get("emulator")`，否则回退模块级单例 `_legacy_emulator_service`。

`inferred`：`get_emulator_service()` 的惰性回退与 loader 的显式注册存在两条路径。正常情况下 loader 已保证 `service.get("emulator")` 命中真实 provider 或 host fallback；`get_emulator_service()` 的 `_legacy_emulator_service` 单例回退是最后兜底（如 loader 未初始化时的早期调用）。两者指向相同实现类但不同实例——非功能问题，但契约测试需覆盖。

---

## 3. 端点契约

### 3.1 配置 CRUD（`observed` + `proposed`）

| 端点 | 方法 | 请求 | 响应 | 成功语义 | 失败语义 |
|------|------|------|------|----------|----------|
| `/api/emulator/get` | POST | `EmulatorGetIn{emulatorId?}` | `EmulatorGetOut{index,data}` | `code=200,status="success"` | `code=500,status="error"` |
| `/api/emulator/add` | POST | 无 | `EmulatorCreateOut{emulatorId,data}` | `code=200,status="success"` | `code=500,status="error"` |
| `/api/emulator/update` | POST | `EmulatorUpdateIn{emulatorId,data}` | `OutBase` | `code=200,status="success"` | `code=500,status="error"` |
| `/api/emulator/delete` | POST | `EmulatorDeleteIn{emulatorId}` | `OutBase` | `code=200,status="success"`；级联清理脚本引用 | `code=500,status="error"`（含脚本锁定时拒绝） |
| `/api/emulator/order` | POST | `EmulatorReorderIn{indexList}` | `OutBase` | `code=200,status="success"` | `code=500,status="error"` |

### 3.2 操作端点（`proposed` — 修复假成功）

| 端点 | 方法 | 请求 | 响应 | 成功语义 | 失败语义 |
|------|------|------|------|----------|----------|
| `/api/emulator/operate` | POST | `EmulatorOperateIn{emulatorId,operate,index}` | `EmulatorOperateOut` | 见下 | 见下 |

**`proposed` 操作结果契约（accepted / operation-id 模式）：**

- **同步校验阶段**（在返回前完成）：UUID 解析、配置加载、类型校验、路径存在性检查。校验失败立即抛异常 → API 返回错误。
- **后台执行阶段**：校验通过后生成 `operationId`，派发后台 task 执行真实 open/close/show，HTTP 立即返回 `accepted`。
- **最终结果通知**：通过 WS `emulator.notice`（`id=EmulatorManager`）推送 `level=info/error` + `operationId`。

响应模型 `EmulatorOperateOut(OutBase)`：

| 字段 | 类型 | 校验失败 | 校验通过（已接受） |
|------|------|----------|--------------------|
| `code` | int | 400 | 200 |
| `status` | str | `"error"` | `"accepted"` |
| `message` | str | 异常摘要（脱敏） | `"操作已提交，结果将通过 WS 推送"` |
| `operationId` | str \| null | null | UUID 字符串 |
| `accepted` | bool | false | true |

**设计理由**：
- open/close 本质长时间操作（受 `MaxWaitTime` 上限 1-9999s 约束，默认 300s），HTTP 同步 await 不可行。
- 同步校验消除「坏配置假成功」：非法 UUID / 不支持类型 / 路径不存在 → 立即 400。
- `accepted` 语义诚实：操作已提交未完成，不声称 success。
- `code=200` 保持旧客户端 `code==200` 兼容；`status="accepted"` 提供诚实区分。
- WS notice 携带 `operationId` 供前端关联最终结果。
- 后台 task 有界：单设备同时仅允许一个 in-flight 操作（拒绝并发重复），task 完成自动清理。

### 3.3 状态查询端点（`proposed` — 隔离）

| 端点 | 方法 | 请求 | 响应 | 成功语义 | 失败语义 |
|------|------|------|------|----------|----------|
| `/api/emulator/status` | POST | `EmulatorGetIn{emulatorId?}` | `EmulatorStatusOut{data}` | `code=200,status="success"` | `code=500,status="error"` |

**`proposed` 隔离规则**：单个 emulator 配置损坏 / 实例失联时，该 emulator 返回空设备字典 `data[eid] = {}`，不中断整列；其余正常 emulator 照常返回。损坏原因记入日志。

### 3.4 搜索端点（`observed`）

| 端点 | 方法 | 请求 | 响应 | 成功语义 |
|------|------|------|------|----------|
| `/api/emulator/emulator/search` | POST | 无 | `EmulatorSearchOut{emulators}` | `code=200,status="success"`；去重 + 稳定排序 |

---

## 4. 操作结果契约设计

### 4.1 选择依据

| 方案 | 可行性 | 选择 |
|------|--------|------|
| 同步 await 真实结果 | ❌ open/close 可达 9999s，HTTP 不可阻塞 | 不选 |
| 假成功 + WS 通知（现状） | ❌ 违反「不得保留假成功」 | 废弃 |
| accepted + operation-id + WS 通知 | ✅ 校验同步、执行异步、结果可关联 | **选定** |

### 4.2 WS 通知扩展（`proposed`，向后兼容）

`WSTaskNoticeData` 新增可选字段：

```python
class WSTaskNoticeData(BaseModel):
    level: Literal["info", "warning", "error"]
    message: str
    operationId: Optional[str] = Field(default=None, description="模拟器操作追踪 ID")
```

- 旧客户端忽略 `operationId`，仍读 `level/message`。
- 前端可通过 `operationId` 关联 HTTP 响应与最终 WS 结果。

### 4.3 并发与有界性

- `EmulatorManager._inflight: dict[str, asyncio.Task]` 按 `"{emulator_id}:{index}"` 跟踪 in-flight 操作。
- 同设备已有未完成操作 → 抛 `RuntimeError`，API 返回 400。
- task 完成后自动从 `_inflight` 移除（`add_done_callback`）。
- 单次操作受 `MaxWaitTime` 上界约束，无无界后台 task。

---

## 5. 状态枚举映射

### 5.1 后端枚举（`observed`）

`app/models/emulator.py: DeviceStatus(IntEnum)`：

| 名称 | 值 | 含义 |
|------|----|------|
| ONLINE | 0 | 在线 |
| OFFLINE | 1 | 离线 |
| STARTING | 2 | 开启中 |
| CLOSEING | 3 | 关闭中 |
| ERROR | 4 | 错误 |
| NOT_FOUND | 5 | 未找到 |
| UNKNOWN | 10 | 未知 |

`app/models/schema.py: DeviceStatus(BaseModel)`（行 1719-1728）：纯文档模型，字段值为 int 常量，与 IntEnum 一致。`DeviceInfo.status: int` 传输值。

### 5.2 前端映射（`observed`）

`frontend/src/api/models/DeviceInfo.ts`：`status: number`（开放数值，不枚举闭合）。`EmulatorOperateIn.operate` 枚举 `open/close/show` 与后端 `Literal["open","close","show"]` 一致。

`observed`：**无枚举漂移**。前后端状态值集合一致（0,1,2,3,4,5,10）。前端不闭合数值枚举，依赖后端契约值。

---

## 6. 边界验证（`proposed`）

| 输入 | 校验点 | 边界 | 错误 code |
|------|--------|------|-----------|
| `emulatorId` | UUID 解析 | 非法 UUID 字符串 | 400 |
| `Info.Type` | `EMULATOR_TYPE_BOOK` | `general/mumu/ldplayer` 之外 | 400 |
| `Info.Path` | `Path.exists()` | 路径不存在 | 400 |
| `Info.MaxWaitTime` | `RangeValidator(1,9999)` | 超范围（config 层已校验） | 500 |
| `operate` | `Literal["open","close","show"]` | schema 层校验 | 422 |
| `index` | 字符串非空 | schema 层 `str` 必填 | 422 |
| 并发同设备操作 | `_inflight` 检查 | 已有 in-flight | 400 |

错误响应脱敏：仅返回 `{type(e).__name__}: {str(e)}`，不回传内部栈或敏感路径细节（路径已在错误消息中，属用户配置可诊断范围）。

---

## 7. 广告屏蔽与强力关闭边界（`observed` / `proposed`）

### 7.1 广告屏蔽（`emulator_manager.py:57` `suppress(Exception)`）

`observed`：`get_emulator_instance` 用 `with suppress(Exception):` 包裹：
1. 广告屏蔽文件操作（`rmtree/mkdir/touch/unlink`）— 可抛 `OSError/PermissionError/FileNotFoundError`。
2. ldplayer `globalsetting` 进程调用 — 可抛 `RuntimeError/asyncio.TimeoutError/OSError`。

`proposed`（修复，在 `emulator_manager.py` 可写范围内）：
- 拆分为具名异常捕获 + `logger.warning`。
- 文件操作捕获 `(OSError, PermissionError)`。
- 进程调用捕获 `(RuntimeError, asyncio.TimeoutError, OSError)`。
- 仅对确属非关键的副作用保留降级；异常可见。

### 7.2 MuMu 强力关闭（`mumu.py`，`observed`，超出可写范围）

`observed`：`MumuManager.close` 的 `finally` 块在 `ForceKillOnClose=True` 时调用 `_force_kill_mumu_processes`，按进程白名单（`mumunxdevice/mumunxmain/mumuvmmheadless`）清理。异常处理为 `(psutil.NoSuchProcess, psutil.AccessDenied, OSError)` + `logger.warning`，已可见。

`observed`（已知缺口）：`mumu.py:376` `find_mumu_nx_window` 用 `with suppress(Exception):` 包裹 `EnumWindows`（回调返回 False 时抛 `pywintypes.error`）。建议改为 `suppress(pywintypes.error)`，但该文件不在 Subagent A 可写范围 → 记入 KNOWN_GAPS。

### 7.3 ldplayer 裸 except（`ldplayer.py:329`，`observed`，超出可写范围）

`observed`：`LDManager.get_adb_ports` 行 329 使用 `except:` 裸捕获。建议改为 `except (psutil.NoSuchProcess, psutil.AccessDenied, OSError)`。不在可写范围 → 记入 KNOWN_GAPS。

### 7.4 自动测试约束

`proposed`：所有后端 deterministic test 使用 fake/stub `DeviceBase`、fake config、monkeypatch `ProcessRunner`/`shutil`/`Path`，不触碰真实目录、注册表、进程、ADB。

---

## 8. 前端 API 再生成说明

`proposed`：本次 schema 变更（新增 `EmulatorOperateOut`、`WSTaskNoticeData.operationId`）需要重新生成前端 API 客户端：

```
cd frontend
yarn dev  # 先启动本地后端
openapi --output ./src/api --client axios  # 从 http://127.0.0.1:36163/openapi.json 生成
```

**禁止手改 `frontend/src/api/**` 生成文件。**

---

## 9. 消费方影响

| 消费方 | 调用方式 | 兼容性 |
|--------|----------|--------|
| 前端模拟器页 | HTTP `/operate` + WS `emulator.notice` | `code=200` 兼容；新增 `operationId/accepted` 字段向后兼容；WS `operationId` 可选关联 |
| `app/plugins/script_adapter.py:390-395` | `get_service("emulator")` → `get_instance` | 不受 operate 契约变更影响 |
| `app/core/config.py:get_emulator_devices_combox` | `EmulatorManager.get_emulator_instance` | 不受 operate 契约变更影响 |
| 任务调度（task_manager） | 通过 `DeviceBase.open/close` 直接调用 | 不经 `operate_emulator`，不受影响 |
