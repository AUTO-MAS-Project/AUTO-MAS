# 配置框架工程约束

本参考用于配置字段、调用点、接口契约及配置框架维护。技术说明见[配置管理文档](https://doc.auto-mas.top/developer/config)。实际签名以当前检出的 `app/config/`、`app/models/config/` 及相邻调用点为准。

来源设计中的节点身份、按需工作区、逐操作事务和 Init 部分成功是框架基础；在此基础上，以下规则描述当前实现。历史规格、历史风格提交和专项示例只作为背景，不能覆盖当前声明及用户已经确认的设计。

## 阅读落点

- 字段定义：`app/models/config/{base,setting,script,queue,plan,emulator,tools,shared}.py`，公共导出及注册表在 `__init__.py`。
- 暂存、事务、锁、激活、序列化：`app/config/core/{node,manager,entry,group,collection}.py`。
- 字段能力：`app/config/{types,shortcuts}.py` 与 `fields/`。
- 接口契约：`app/config/wire.py`、所属 `app/api/` 模块及公共 `app/models/schema.py`。
- 启动、升级：`app/core/config/manager.py`、`app/core/config/upgrade.py`；前端时间转换为 `frontend/src/utils/configDateTime.ts`，Electron 启动读取为 `frontend/electron/services/backendConfig.ts`。

`app/config/` 仅提供配置基础机制；应用级配置启动、业务 CRUD、专项适配、升级和备份由 `app/core/config/` 实现，包入口创建全局 Config。不能将这些应用封装放进基础框架的 application 子包，也不能让 core 只剩实例化空壳。此职责拆分不改变节点身份、激活顺序或事务契约。

应用主路径由 Config 的 Path 属性统一提供，资源用 `Config.resource_path / ...`，配置和用户数据分别用 `Config.config_path`、`Config.data_path` 等。Runtime 的源码目录可能与工作目录不同，不能混用；工具需要主路径时由调用方传入，不新增路径转发函数，也不让基础框架或 utils 导入 Config。

普通字段与调用点任务按以下规则处理；涉及 `app/config/` 的设计变更时，先说明问题、必要性、行为差异及方案，由用户确认后实施。已有明确授权的方案继续执行，不重复询问，也不将普通适配扩大为框架重构。

## 配置声明与类型

1. 配置对象使用 `ConfigEntry`（业务层通常继承 `DomainEntry`），分组使用 `ConfigGroup`，集合使用 `ConfigCollection[T]`；公开类型从 `app.config` 导入。
2. 配置模型是业务字段、默认值、约束和中文 `Field(description=...)` 的唯一来源。分组及可变默认值使用 `default_factory`；已有业务字段不为统一风格批量改名。
3. 嵌套集合以 `collection(AllowedType, ...)` 声明，注解提供静态类型，参数登记具体允许类型。根集合通过 `ConfigCollection[T].build(...)` 构造；`build()` 同时提供 `parent/uid/payload/file/name` 等参数的类型提示。
4. 类级常量使用 `ClassVar`，实例私有状态使用 `PrivateAttr`。字段定义位于类体，任务、票据、工作区及暂存队列属于运行时状态。
5. 基础校验由 Pydantic 类型、`Literal`、枚举和 `Field` 约束承接。`Field(ge=..., le=...)` 是拒绝越界输入，并非截断；纠正规则通过标准 `Annotated` 类型复用，不添加外置校正回调参数或第二套校验器列表。
6. 固定结构声明准确的 Pydantic 子模型。开放映射使用准确的键值类型，允许缺键，由消费方补齐运行时所需项；不借缺省语义放宽为 `Any`，不假定映射已有全部键。
7. 继承并覆写少量分组或集合是有效业务建模方式。静态可变属性收窄经实际验证后可在具体声明处作带说明的精确豁免；不以此全局关闭诊断或扩展基类泛型机制。

## 标准字段能力

- **路径**：内存为 `Path | None`，声明为 `Annotated[Path | None, path_policy(kind=..., extensions=..., must_exist=..., blocked_dirs=...)]`。`kind` 为 `file/folder/any`；后缀是具体扩展名列表或元组，支持复合后缀，不使用通配符；阻止目录接受字符串、`Path` 或框架预设。复用 `FilePath/FolderPath/ScriptRootPath/ExecutablePath/LoosePath` 时核对其存在性和目录边界。
- 路径保留绝对化、环境变量、符号链接及 Windows 快捷方式归一化。要求存在且允许目录时，仅在去掉最后一个后缀后确有合法目录才接受修正；现存带点目录完整保留。要求存在的失效值清空为 `None`。路径 UI 提示从同一声明派生，阻止目录由后端执行。
- **日期时间**：在 `ConfigGroup` 声明完整 `datetime`。Pydantic 层将默认值、冷态输入和热态提交统一存为 UTC；无时区输入始终解释为 UTC。属性读取时按 `tz(timezone_or_callable)` 转换，缺省读取时区为 UTC+8；回调接收分组，返回固定偏移 `datetime.timezone`，同步只读且无自身字段递归依赖。
- 日期时间序列化直接导出原对象的 UTC 存储值，不复用属性读取、动态时区或校正逻辑；日期和钟点展示由 `ui(format=...)` 表达，保留完整值。固定偏移不等于完整夏令时支持；相关边界已有 TODO，不擅自增加日期裁剪或改变无时区语义。
- **加密**：`Annotated[str, encrypted()]`，标记位于注解元数据末尾。字段属性读取为明文，落盘为密文，采用同设备多用户可解密的算法；跨设备迁移使用明文导出。解密失败保留原始不可用内容，提示由前端决定，后端不替换提示文本。
- **字符串**：复用 `JsonDictString/JsonListString/UrlString/WindowsNameString/KeyboardKeyString/CliArgumentString/CliArgumentListString` 的既定策略。JSON 字符串保持字符串；键位转小写，非法值通过 `PydanticUseDefault` 回退到该字段 `Field` 中声明的合法默认键位。
- **引用**：`Annotated[UUID | str, ref(target_name, ...)]`。目标是已登记的命名集合；`entry_types` 通过 `isinstance` 接受子类。删除及 `reload_type/replace_type` 后统一重校验，复用 `SET_DEFAULT/RESTRICT/CASCADE/CUSTOM` 策略。`display_field="Info.Name"` 的选项值为 UUID、展示值来自目标字段；候选值和类型过滤由框架 UI 元数据统一计算。
- **响应式**：`Virtual[T]` 与同步 `@virtual_field("Group.Field")` 配对，计算值只读；`Trigger[bool]` 或 `Trigger[Literal[...]]` 与 `@trigger_field(...)` 配对。触发器立即分派，异步处理另建任务，不能当作普通信号的事务内修改或假定 `commit()` 等待它完成。
- **显隐**：统一使用 `ui(visibility=...)` 或 `@ui_visibility(...)`；`SHOW/HIDE/DISABLE/MASKED` 分别表达正常、隐藏、禁用与掩码。所有子项隐藏时组隐藏，掩码限具体字段。`UI_MASKED_VALUE` 原样回传表示保持现值，不是待保存的真实内容。UI 元数据能力不自动授权增加动态表单或触发器交互。
- **字段兼容**：统一使用 `legacy(group=..., name=..., convert=...)`，在输入准备和激活时集中转换并校验；显式目标字段（含 `None`）优先。不新增并行别名、放宽类型标记或 API 搬运逻辑。

## 生命周期、赋值与集合

1. 构造及 `model_validate()` 产生冷态对象，校验与字段赋值不激活、不发送运行时信号、不保存；引用目标存在性在热态校验。`build(payload=...)` 保留原始待激活载荷，普通属性尚未反映其内容。正常文件启动使用 payload 重建集合成员，不把旧冷态成员作为激活结果直接发布。
2. `activate()` 依次经历 `INACTIVE → INITIALIZING → ACTIVE`。普通路径按字段或成员建立局部回退边界，成功部分可保留，最后抛出聚合错误；独立根激活抛聚合错误时可能已部分提交。`activate(fast_init=True)` 只扩大当前 Entry 的字段事务边界：任一字段校验或 Init 信号失败时，整次尝试先回退，再从首字段执行原逐字段路径；不保留快速尝试中的成功部分，也不改变严格校验顺序和即时信号语义。嵌套 Entry 各自尝试和回退，父事务失败则一起恢复冷态及待激活载荷。
3. 引用目标先登记、激活，再激活依赖方；启动顺序由 `app/core/config/manager.py` 编排。只有根节点关联 `.yaml/.yml` 文件，`payload` 与 `file` 互斥，UUID 在登记前确定；子集合随根持久化。
4. 热态普通字段赋值只 stage，`await node.commit()` 才应用。仅支持整字段赋值；列表、字典及嵌套可变值先复制修改，再整字段赋值。原地 `append`、下标写入及内部对象修改绕过校验、锁、信号和回退，后续 `commit()` 不会补救。深层隔离是已标注的待完善边界，不能宣称已支持。
5. `await entry.update(same_type_cold_entry)` 依据 Entry 与 Group 的 `model_fields_set` 更新实际提供字段并自动提交，默认检查显隐，跳过虚拟项；不承接嵌套集合。外部请求保持默认显隐检查，内部明确需要时使用 `check_visibility=False`。
6. 集合使用 `add/remove/set_order/add_type/remove_type/reload_type/replace_type` 加 `commit()`。`add(payload=...)` 返回预分配 UUID；提交成功后才可取得成员。`replace_type` 由调用方转换载荷，保留 UUID 和顺序，发送类型替换事件，不冒充 remove；新实例不继承旧实例订阅。
7. 复制通过 `add(payload=..., regenerate_uuids=True)` 等现有入口完成。该参数递归激活嵌套集合成员，仅重生身份，不重写引用值；关联复制需要明确的 UUID 映射。正常加载保留默认 `False`。

## 事务、工作区与业务锁

1. 默认事务边界是一个 op 及其直接信号链；单次 `commit()` 批次中的各 op 独立成功或回退，失败聚合后报告。显式 `async with config_manager.transaction()` 使其内部修改共享整体边界，同 Task 嵌套复用事务，不建立保存点；需要局部回退时使用 `transaction(new_boundary=True)`。
2. 异常离开最外层事务才整体回退。在事务内部捕获异常后正常退出不会自动使根事务失败；需要回退的异常在边界外处理。通知、设备、数据库及外部文件副作用不受配置事务回退保护。
3. 全局执行入口先于节点提交锁获取，覆盖完整 commit 批次、显式事务和保存；保持全局单事务模型。同 Task 或无 Task 时同 Thread 可重入；其他执行者排队，取消等待释放登记及已交接资格。普通线程同步入口可阻塞，事件循环线程的同步入口在竞争时抛错。
4. 事务、Init 和节点提交标记同时检查实际 Task/Thread 与生命周期。直接调用、直接 `await` 的关联方法共享事务；子 Task 即使继承 `ContextVar` 也没有参与资格。父事务等待一个需要提交的独立子 Task 会形成循环等待；关联修改留在同 Task，独立工作在事务后启动。
5. 属性读取为有效 Init 工作区 → 有效普通工作区 → live；未建立工作区的节点读 live，独立任务读 live。身份与业务引用始终使用 live 节点，工作区在事务后失效。
6. 暂存仅放 live，按执行者和普通/Init 作用域隔离；赋值及提交位于同一作用域。当前作用域为空但同执行者其他作用域有暂存会报错。回调返回、事务退出前有本链未提交暂存会报错并回退；Task 结束清理遗留。取消归还已回退和未执行操作，不自动重试或转移别人的暂存。
7. `model_dump()` 导出调用对象的存储状态：live 对象保持 live，工作区检查需显式 `node.effective.model_dump()`。API 虚拟值/UI 元数据可动态求值，不能将其视为普通存储字段快照。
8. S 锁拒绝覆盖范围内全部热写；X token 持有上下文可直接修改 live 并提交，任务不建立副本再整体回写。票据在 `finally` 中通过签发节点 `unlock(ticket)` 释放，默认级联；结构操作另有未锁定前置条件。X token 可随上下文继承，与事务真实所有者是两套判定。

### 快速初始化与激活状态

- `fast_init` 是显式的启动优化开关，不是普通热态提交模式。它只作用于当前 Entry 的字段初始化循环；集合成员、嵌套 Entry 和普通运行时 `commit()` 仍使用各自既有边界。
- 快速尝试失败后，事务先撤销工作区、信号工作区和受管关联修改，再从第一个字段进入逐字段流程。Init 接收者或第三方服务可能被调用两次，框架不扫描、去重或回滚外部副作用。
- 激活标记在构造时从直接父节点承接，`build()` 与 `activate()` 不再额外传递标记。节点自己的 `NodeState` 与整棵激活树的进行状态分开维护。
- 初始化中的热态锁、触发器、公开订阅、删除守卫、file/name 登记等只限制本次激活树；树外已稳定节点按原热态规则处理。冷态字段校验和激活内部的引用订阅继续执行。
- `fast_init` 不冻结或替换节点、分组及成员实例的公开身份；工作区只在事务期间作为有效视图存在，集合的 `data/order` 仍按既有事务状态读取。

## 信号

- `Class.connect()` 订阅具体类，`node.connect()` 订阅实例；子类信号独立。过滤参数为 `phase/kind/group/field`，集合不接受 group/field。默认 runtime，初始化使用 init；事件包括字段 set/init_set 及集合添加、删除、排序、类型增删、reload、replace。
- Blinker 先同步调用包装器，再逐个 await 返回结果；不扩展并发派发或依赖接收者顺序。关联配置修改在接收者内直接 await 提交，独立 Task、`gather()` 不属于同一事务。
- 公开订阅使用弱引用，接收者需有稳定生命周期且可挂载包装器；函数或持有的可调用对象适用。解除订阅使用原接收者及相同过滤参数。
- 订阅变更参与信号工作区及回退。Blinker 无公开完整订阅枚举，当前在工作区创建函数内自建有效订阅枚举，再用 connect 重建独立索引；保留这一兼容边界，不改为浅拷贝索引或另造信号系统。

## 持久化与导出

1. 普通事务成功合并后递增涉及根的修改代次，关闭上下文再登记保存；Init 只并入父工作区。单保存执行器按约 50ms 安静期合并请求，正常全量扫描，跳过未激活根。
2. 保存取得同一全局入口并复核期限，从导出到同步原子写入完成保持占用；新请求更新期限，不取消正在写入的任务。回退不新增请求，也不清除已有成功请求。无事件循环时保留请求，后续异步入口或 flush 接续。
3. 各根导出与写入失败独立隔离；IO 首次失败后按 1/2/4/8/16 秒各重试一次，读取最新稳定值。非 IO 错误仅在本根修改代次变化或 flush 时重试；其他根修改不重置预算。耗尽后暂停，flush 失败不重置整组预算，成功清除记录。`persistence_errors` 只读快照不含载荷。
4. `commit/update/activate` 完成内存操作，不等于落盘。事务外 `await config_manager.flush()` 跳过防抖，尝试全部根，聚合报告失败；当前事务及其普通回调内调用报错。保存失败不回滚内存，多个文件无跨文件原子性。
5. 公开 `ExportContext` 从 `app.config` 导入，使用 `audience="api"/"persist"/"export"`：API 为明文、响应式及 UI 显隐；persist 为密文持久字段；export 为明文持久字段。持久化和迁移导出不含虚拟/触发器。不要引入额外 `if_decrypt` 开关或复用 wire 内部同名上下文。
6. `model_dump()` 默认 JSON/API；`await to_dict()` 校验 ACTIVE 和未删除，使用 persist，但不写文件。Entry 的 Python 模式按子组默认上下文处理，显式加密受众使用 JSON 模式。JSON 中 Path→str、None→null，日期时间导出 UTC 原始存储值。
7. 事务外 `await config_manager.export(target_directory)` 按注册根导出稳定明文 YAML，从内存读取、保留文件布局，独立于 flush；拒绝覆盖运行文件。ZIP 与其他备份内容由外层服务负责。解除文件登记不执行最后保存，引用池登记与文件登记相互独立。

## API、前端与历史升级

- 配置输入输出使用缓存的 `ConfigInput[T]/StrictConfigInput[T]/ConfigPayload[T]` 或 `config_contract()`，纯契约不激活配置或执行持久化。端点专用模型在路由模块顶层，公共跨层契约在单文件 `schema.py`；业务和配置层不导入路由。
- 请求转字典使用 `model_dump(exclude_unset=True)`；保留显式 null，不用 `exclude_none`，不把未提供字段的默认 None 写回。是否接受 null 由具体字段校验决定，敏感字段遗漏与掩码回传保持原值。
- 集合输出是 `order: [{uid, type}] + data: {uuid: Entry}`。注册表只登记配置类及业务关系，不恢复 `schema_class` 或手写配置字段表。路径/方法/包络/MCP 标签的变更按外部契约处理，前端客户端通过 OpenAPI 生成器更新。
- 前端复用 `configDateTime.ts`，内存和回传保留完整带偏移 ISO；非空时刻字段清空按约定得到 00:00 的完整时间，nullable 字段按自身语义处理。框架元数据本身不构成启用动态表单的需求。
- 一次性升级由启动流程处理历史数据库检查点、专项预处理、JSON→YAML 转换及依赖激活；无时区历史日期按原业务时区补齐后转 UTC。早期格式可由历史适配代码延迟调用旧实现，正常业务只使用当前框架。
- 七个映射为 `Config.json→setting.yaml`、`ScriptConfig.json→scripts.yaml`、`PlanConfig.json→plans.yaml`、`QueueConfig.json→queues.yaml`、`EmulatorConfig.json→emulators.yaml`、`ToolsConfig.json→tools.yaml`、`GameSignAccounts.json→game_sign_accounts.yaml`。保留 UUID、顺序、引用、凭据，独立账号文件优先。
- `config/legacy-json/` 保存原件，迁移记录跟踪进度，临时写入及校验后替换，冲突停止、完成文件不重复导入。v1.11→v2.0 在全部文件迁移/激活/flush 成功后推进，失败阻止业务启动；无数据库同样处理，首次安装直接生成 YAML。正常 YAML 运行不因 JSON 再出现而回退导入。

## 验证落点

调用点清点覆盖受版本控制的运行入口与延迟初始化链，包括根目录 `main.py`、`app/` 和相关启动脚本；仅扫描 `app/` 会遗漏启动回调。检查导入别名、动态取方法及分组字段访问，区分普通字典/第三方对象的同名方法、公开集合操作与历史升级适配器。

按变更选择隔离验证：冷态无副作用、缺省/null/掩码、UTC 存储与导出、锁票据、信号链回退、Init 部分成功、逐 op 与显式事务差异、跨 Task 排队与暂存隔离、保存失败与 flush、迁移重试及冲突、OpenAPI 字段与生成类型。目录和配置文件使用临时副本，设备、通知及外部脚本使用替身。

框架类型检查不新增诊断；受影响业务调用使用准确类型，已有逐处确认的继承收窄豁免保留。一次性测试产物遵循 `tests/AGENTS.md` 和根目录提交规则；不把验证脚本或本机路径写进 Skill 的公共入口。
