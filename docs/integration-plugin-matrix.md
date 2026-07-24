# 全插件集成矩阵

本文记录 `integration/dev-v2-dev-all-plugins` 工作区在 2026-07-22 的源码构建契约。数据直接取自 `res/integration-snapshot.json`、各源码目录的 `pyproject.toml` 和 Git 工作区状态；它用于确定必须构建的 23 个 plugin distribution 与必须发现的 21 个 `auto_mas.plugins` entry point，不代替 wheelhouse 完成校验、隔离导入、启动或业务冒烟测试。

v6 Alpha c2 已生成并通过 Electron 发布链使用的同一套严格 manifest/runtime-lock 校验器。产物级事实以 `build/w/c2/manifest.json`、`build/w/c2/runtime-lock.json` 和 `res/integration-snapshot.json` 为准；旧 r11/r12 候选只保留作审计材料。c2 已进一步通过洁净离线安装以及直接、真实路由顺序两种入口导入门禁。

## 来源快照

| 代号 | 来源仓库 / 工作树 | Git 快照 | 当前状态与纳入方式 |
| --- | --- | --- | --- |
| `OFFICIAL-DEV_V2` | `upstream/dev_v2`；集成目标为 `AUTO-MAS-workspace/worktrees/all-plugins-integration` | `b5e872815a3ea5eef81fc3fd34eb0dc71db32d4e` | 官方宿主基线。集成工作树以该 commit 为 HEAD 且 dirty；Core 含未提交集成修改，两个 OK adapter 的包路径保持基线状态。 |
| `OFFICIAL-DEV` | `upstream/dev` | `e012f284374021e227f3d85e822df612b248b345` | 官方 `dev` 快照已验证为上述 `dev_v2` 快照的祖先；其改动已被基线覆盖，不重复计算 distribution。 |
| `BROWSER-DRAFT` | `AUTO-MAS-workspace/worktrees/browser-capability`，再复制到集成目标的 `plugins/browser` | `9dd56de759faafe45a071c94f40d1f1369c7c0eb`，`feat/browser-capability` | 源工作树 dirty，浏览器插件目录 untracked；属于本地草稿，集成副本同样 untracked，不伪称为该 commit 中已提交的源码。 |
| `HSR` | `plugins/automas-hsr`；`origin=https://github.com/AUTO-MAS-Project/automas-hsr.git` | `2430286c09ff3dd8cdd1d2e8aec8a96f49799b28`，`main` | clean，官方仓库 checkout。 |
| `M9A` | `plugins/automas-m9a`；`origin=https://github.com/AUTO-MAS-Project/automas-m9a.git` | `c6edfc6a2b4f98aefabd17ce052592c27aa801f3`，`main` | clean，官方仓库 checkout。 |
| `MAAFW` | `plugins/automas-maafw`；`origin=https://github.com/AUTO-MAS-Project/automas-maafw.git` | `14382d877b384c61522ae5c9e3ee586dad5c289f`，`main` | 仓库 dirty；同时包含官方已提交包、modified 本地草稿与 untracked 本地草稿，逐项见下表。 |
| `MXU-IMPORT` | `plugins/automas_mxu_import`；`origin=https://github.com/AUTO-MAS-Project/automas_mxu_import.git` | `a501a10181d8193df42f6953763c713a934c2382`，`dev` | clean，官方仓库 checkout。 |
| `MAAEND` | `plugins/automas-maaend-adapter`；`origin=https://github.com/AUTO-MAS-Project/automas-maaend-adapter.git` | `2acb9ee827e653779e3ce143b8d3c418e259c167`，`dev` | **dirty**：`src/maaend_adapter/adapter/runtime.py` 有 ADB / Win32 隐藏绑定兼容修复，`tests/` 为新增验证；构建必须包含当前工作树，不能只按 commit 还原。 |
| `MAA-SCRIPT` | `plugins/automas_script_maa`；`origin=https://github.com/AUTO-MAS-Project/automas_script_maa.git` | `a561607b1fc8e3c3da3f3abfc3b3c2bb87527b6a`，`master` | Git 状态未列出源码改动，官方仓库 checkout。 |

以上是 9 个来源范围；集成工作树是汇总目标，不另算第 10 个来源。以下所有可加载项使用 entry-point group `auto_mas.plugins`。表中的 distribution、version、entry-point name/value 和依赖范围均保持对应 `pyproject.toml` 的原值；是否已形成完整产物不由本表预判。

## 分组计数

| 构建分组 | 来源范围 | Distribution | Entry point | 备注 |
| --- | --- | ---: | ---: | --- |
| 宿主随附源码 | `OFFICIAL-DEV_V2`、已包含的 `OFFICIAL-DEV`、`BROWSER-DRAFT` | 4 | 4 | Core、Browser、两个 OK adapter。 |
| HSR | `HSR` | 4 | 3 | 含 1 个无 entry point 的 aggregate。 |
| M9A | `M9A` | 2 | 1 | 含 1 个无 entry point 的 aggregate。 |
| MaaFW | `MAAFW` | 10 | 10 | 官方已提交包与本地草稿共同构成当前范围。 |
| 新增官方插件 | `MXU-IMPORT`、`MAAEND`、`MAA-SCRIPT` | 3 | 3 | 三个独立仓库各提供 1 个 entry point；MaaEnd 使用当前 dirty 兼容修复。 |
| **合计** | **9 个来源范围** | **23** | **21** | 与 `res/integration-snapshot.json` 的 wheelhouse contract 一致。 |

## 宿主随附源码（4 个 distribution / 4 个 entry point）

| 来源状态 | Distribution / version | Group | Entry-point name → value | 分类 | 关键依赖范围 |
| --- | --- | --- | --- | --- | --- |
| `OFFICIAL-DEV_V2@b5e87281`，Core 路径 modified，本地集成稿 | `auto-mas-core` `6.0.0a1` | `auto_mas.plugins` | `auto_mas_core` → `auto_mas_core.plugin:Plugin` | 系统插件 / SDK | 无 |
| `BROWSER-DRAFT@9dd56de7`，dirty + untracked | `automas-plugin-browser` `0.1.0` | `auto_mas.plugins` | `browser` → `automas_plugin_browser.plugin:Plugin` | 普通 capability 插件；以 locked system instance 随宿主启用，但**不是 ScriptType，也不是脚本 adapter** | `auto-mas-core>=6.0.0a1`；`psutil>=7.0,<8`；`pydantic>=2.11,<3`；`selenium>=4.44,<5` |
| `OFFICIAL-DEV_V2@b5e87281`，包路径 clean，官方基线 | `automas_plugin_okww_adapter` `0.0.1` | `auto_mas.plugins` | `okww_adapter` → `okww_adapter.plugin:Plugin` | 脚本 adapter：`Okww` | 无 |
| `OFFICIAL-DEV_V2@b5e87281`，包路径 clean，官方基线 | `automas_plugin_ok_script_adapter` `0.1.0` | `auto_mas.plugins` | `ok_script_adapter` → `ok_script_adapter.plugin:Plugin` | 脚本 adapter：`OkScript` | 无 |

## HSR（4 个 distribution / 3 个 entry point）

| 来源状态 | Distribution / version | Group | Entry-point name → value | 分类 | 关键依赖范围 |
| --- | --- | --- | --- | --- | --- |
| `HSR@2430286c`，clean，官方 | `automas-script-hsr` `0.1.0` | `auto_mas.plugins` | `automas_script_hsr` → `automas_script_hsr.plugin:Plugin` | 脚本 adapter：`HSR`，并提供 HSR registry capability | `jinja2>=3.1`；`pydantic>=2` |
| `HSR@2430286c`，clean，官方 | `automas-hsr-adapter-sra` `0.1.0` | `auto_mas.plugins` | `automas_hsr_adapter_sra` → `automas_hsr_adapter_sra.plugin:Plugin` | capability / HSR SRA 后端 adapter；不新增 ScriptType | `automas-script-hsr>=0.1.0,<0.2.0` |
| `HSR@2430286c`，clean，官方 | `automas-hsr-adapter-m7a` `0.1.0` | `auto_mas.plugins` | `automas_hsr_adapter_m7a` → `automas_hsr_adapter_m7a.plugin:Plugin` | capability / HSR M7A 后端 adapter；不新增 ScriptType | `automas-script-hsr>=0.1.0,<0.2.0`；`PyYAML>=6` |
| `HSR@2430286c`，clean，官方 | `automas-hsr` `0.1.0` | — | **无 entry point** | aggregate / 依赖集合，不是可加载插件 | `automas-script-hsr>=0.1.0,<0.2.0`；SRA/M7A adapter 均为 `>=0.1.0,<0.2.0` |

## M9A（2 个 distribution / 1 个 entry point）

| 来源状态 | Distribution / version | Group | Entry-point name → value | 分类 | 关键依赖范围 |
| --- | --- | --- | --- | --- | --- |
| `M9A@c6edfc6a`，clean，官方 | `automas-script-maafw-pack-m9a` `0.1.2` | `auto_mas.plugins` | `automas_script_maafw_pack_m9a` → `automas_script_maafw_pack_m9a.plugin:Plugin` | capability / MaaFW M9A project-pack 声明；不新增 ScriptType | `automas-script-maafw>=0.1.4`；`pydantic>=2` |
| `M9A@c6edfc6a`，clean，官方 | `automas-m9a` `0.1.2` | — | **无 entry point** | aggregate / 依赖集合，不是可加载插件 | `automas-maafw-interface>=0.1.1`；`automas-maafw-project-update>=0.1.0`；`automas-maafw-agent-env>=0.1.0`；`automas-maafw-runner>=0.1.1`；ADB `>=0.1.0`；Win32 `>=0.1.1`；`automas-script-maafw>=0.1.4`；M9A pack `>=0.1.2` |

## MaaFW（10 个 distribution / 10 个 entry point）

`MAAFW` 仓库整体 dirty。下表的“包路径 clean”只表示该 package 目录未出现在 `git status --short` 中，并不把整个仓库描述成 clean。

| 来源状态 | Distribution / version | Group | Entry-point name → value | 分类 | 关键依赖范围 |
| --- | --- | --- | --- | --- | --- |
| `MAAFW@14382d87`，包路径 clean，官方已提交源码 | `automas-maafw-interface` `0.1.1` | `auto_mas.plugins` | `automas_maafw_interface` → `automas_maafw_interface.plugin:Plugin` | capability / `maafw.interface.v1` service | `json5>=0.9`；`pydantic>=2` |
| `MAAFW@14382d87`，包路径 clean，官方已提交源码 | `automas-maafw-project-update` `0.1.0` | `auto_mas.plugins` | `automas_maafw_project_update` → `automas_maafw_project_update.plugin:Plugin` | capability / project-update service | `aiofiles>=23`；`automas-maafw-interface>=0.1.0`；`httpx>=0.27`；`packaging>=23` |
| `MAAFW@14382d87`，package modified，本地草稿 | `automas-maafw-agent-env` `0.1.1` | `auto_mas.plugins` | `automas_maafw_agent_env` → `automas_maafw_agent_env.plugin:Plugin` | capability / agent environment service | `automas-maafw-interface>=0.1.0`；`pydantic>=2` |
| `MAAFW@14382d87`，package modified，本地草稿 | `automas-maafw-runner` `0.2.0` | `auto_mas.plugins` | `automas_maafw_runner` → `automas_maafw_runner.plugin:Plugin` | capability / isolated runner service | Agent Env `>=0.1.1`；Interface `>=0.1.1`；Runtime Pool `>=0.1.0`；`json5>=0.9`；`packaging>=23`；`pydantic>=2` |
| `MAAFW@14382d87`，包路径 clean，官方已提交源码 | `automas-maafw-controller-adb` `0.1.0` | `auto_mas.plugins` | `automas_maafw_controller_adb` → `automas_maafw_controller_adb.plugin:Plugin` | capability / ADB controller provider | `pydantic>=2` |
| `MAAFW@14382d87`，包路径 clean，官方已提交源码 | `automas-maafw-controller-win32` `0.1.1` | `auto_mas.plugins` | `automas_maafw_controller_win32` → `automas_maafw_controller_win32.plugin:Plugin` | capability / Win32 controller provider | `automas-maafw-interface>=0.1.0`；`pydantic>=2` |
| `MAAFW@14382d87`，package untracked，本地草稿 | `automas-maafw-project-store` `0.1.0` | `auto_mas.plugins` | `automas_maafw_project_store` → `automas_maafw_project_store.plugin:Plugin` | capability / versioned project-store service | `json5>=0.9` |
| `MAAFW@14382d87`，package untracked，本地草稿 | `automas-maafw-runtime-pool` `0.1.0` | `auto_mas.plugins` | `automas_maafw_runtime_pool` → `automas_maafw_runtime_pool.plugin:Plugin` | capability / multi-version runtime-pool service | `packaging>=23` |
| `MAAFW@14382d87`，package modified，本地草稿 | `automas-script-maafw` `0.1.5` | `auto_mas.plugins` | `automas_script_maafw` → `automas_script_maafw.plugin:Plugin` | 脚本 adapter：`MaaFW`；同时提供 `maafw.registry.v1` | Agent Env `>=0.1.0`；ADB `>=0.1.0`；Win32 `>=0.1.1`；Interface `>=0.1.1`；Project Update `>=0.1.0`；Runner `>=0.2.0`；`pydantic>=2` |
| `MAAFW@14382d87`，package untracked，本地草稿 | `automas-script-maafw-managed` `0.1.0` | `auto_mas.plugins` | `automas_script_maafw_managed` → `automas_script_maafw_managed.plugin:Plugin` | 脚本 adapter：`MaaFWManaged` | Script MaaFW `>=0.1.5`；Runner `>=0.2.0`；Interface `>=0.1.1`；Project Update / Store / Runtime Pool 均 `>=0.1.0` |

## 新增官方插件（3 个 distribution / 3 个 entry point）

| 来源状态 | Distribution / version | Group | Entry-point name → value | 分类 | 关键依赖范围 |
| --- | --- | --- | --- | --- | --- |
| `MXU-IMPORT@a501a101`，clean，官方 | `automas-plugin-mxu-import` `0.1.0` | `auto_mas.plugins` | `mxu_import` → `automas_plugin_mxu_import.plugin:Plugin` | capability / `mxu.import.v1`，将 MXU 配置转换为 MaaFW 任务快照 | `automas-maafw-interface>=0.1.1`；`pydantic>=2` |
| `MAAEND@2acb9ee8`，**dirty 兼容修复** | `automas_plugin_maaend_adapter` `0.0.2` | `auto_mas.plugins` | `maaend_adapter` → `maaend_adapter.plugin:Plugin` | 脚本 adapter：`MaaEnd`；运行生命周期复用 MaaFW adapter | `automas-script-maafw>=0.1.1`；`pydantic>=2` |
| `MAA-SCRIPT@a561607b`，官方源码状态未列出改动 | `automas_script_maa` `0.0.5` | `auto_mas.plugins` | `script_MAA` → `script_maa.plugin:Plugin` | 脚本 adapter：`MAA` | `pydantic>=2.0`；`auto-mas-core>=5.2.0` |

## 数量与 bootstrap 约束

- 源码构建契约为 **23 个 distribution / 21 个可加载 entry point**：宿主 4/4 + HSR 4/3 + M9A 2/1 + MaaFW 10/10 + 新增官方插件 3/3。
- `automas-hsr` 与 `automas-m9a` 是两个无 entry point 的 aggregate；它们计入 23 个直接输入 distribution，但不计入 21 个可加载项。
- HSR/M9A aggregate 只能用作依赖集合，**不能作为唯一 bootstrap 项**。bootstrap 清单、安装状态和隔离导入校验必须显式覆盖实际提供 entry point 的 21 个 distribution；aggregate 自身“已安装”不能证明 entry point 已安装且可发现。
- `automas-m9a` `0.1.2` 的依赖集合没有声明当前本地新增的 Project Store、Runtime Pool 和 Managed Script adapter，也不代表三个新增官方仓库，因此不能作为完整插件集合的替代清单。
- Browser 只发布 `browser.runtime.v1` 浏览器能力，并以普通插件生命周期运行；它不是 HSR/M9A/OK/MaaFW/MAA/MaaEnd 的 ScriptType，不应混入脚本 adapter 数量。
- 完整 wheelhouse 除 23 个直接 plugin distribution wheel 外，还必须包含宿主和插件锁定依赖的完整运行时 wheel 闭包；因此最终 `.whl` 文件总数不应与 23 直接画等号。
- 当前源码范围没有额外的 Emulator plugin distribution 或 entry point；Emulator 宿主兼容回退属于另一条运行时验证链路，不改变 23/21 计数。

## v6 Alpha c2 的产物判定

`res/integration-snapshot.json` 当前声明以下交付契约：

- `manifest_schema_version = 3`
- `runtime_lock_schema_version = 1`
- `plugin_distribution_count = 23`
- `plugin_entry_point_count = 21`

`res/integration-snapshot.json` 还固定 `wheel_count=127`、Core `6.0.0a1` 及两个文件哈希。实际 c2 目录逐项核对结果如下：

| 项目 | c2 实际值 |
| --- | --- |
| wheel / 目录总文件 | 127 / 131 |
| host runtime / plugin runtime / plugin | 95 / 9 / 23 |
| 宿主直接固定依赖 | 31 |
| plugin distribution / entry point | 23 / 21 |
| Core distribution | `auto-mas-core==6.0.0a1` |
| `manifest.json` SHA-256 | `7123F7CA99A843E34C189F99744CECB568BD82A348B1457ED634438CECAD199B` |
| `runtime-lock.json` SHA-256 | `8A1CA0B31634AE2E63E55440C34C3A38998E3D20F68CA55CB6E620DA94EF3069` |

31 是宿主 `pyproject.toml` 中直接固定的依赖输入；其完整传递闭包是 95 个宿主运行时 wheel。`runtime-lock.json` 列出的 23 个插件 distribution 与上面各源码目录的名称和版本一致，其中 `automas-hsr`、`automas-m9a` 两个 aggregate 没有 entry point，其余 21 个各提供一个唯一的 `auto_mas.plugins` 入口。

洁净运行时结果取自 `build/clean-runtime-alpha-c2/verification-route-first-final.json` 与 `verification-direct-final.json`：95/95 宿主、32/32 插件 target、21/21 入口和 15/15 no-config 契约通过，`errors=[]`、`exit_code=0`，无 source/editable 回退。

Config v2 在此 Alpha 中默认是 `shadow`：旧 JSON 保持权威，只做预检和安全影子输出；上述插件矩阵和洁净运行时结果不能解释为 authoritative 模式已开放。当前也没有执行真实游戏、真实账号或真实设备 E2E，因此各脚本与 ADB/Win32 控制器仍需在受控账号、设备上完成业务验收。
