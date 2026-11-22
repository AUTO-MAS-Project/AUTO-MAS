# MFW、M9A、MSS 插件化说明

通用 MFW（运行任意 `interface.json` 项目的 MaaFramework 引擎）和 M9A、MSS 两个专项不再内置在宿主里，改由插件包提供。本文写宿主一侧：哪些包、升级时发生什么、装不上时怎样、怎样回退。插件自身的设计见积木仓库 [AUTO-MAS-MaaFW](https://github.com/AUTO-MAS-Project/AUTO-MAS-MaaFW) 与三个专项仓库。

## 包与插件

| 发行包 | 插件 ID / 导入名 | 作用 |
| --- | --- | --- |
| `auto-mas-maafw-interface` | 库 `maafw_interface` | interface 解析、建运行计划、Win32 窗口匹配规则 |
| `auto-mas-maafw-native` | 库 `maafw_native` | 原生库识别与布局 |
| `auto-mas-maafw-agent-env` | `maafw_agent_env` | agent 环境与运行池 |
| `auto-mas-maafw-runner` | `maafw_runner` | 运行（worker、设备、桌面游戏） |
| `auto-mas-maafw-project-update` | `maafw_project_update` | 项目副本、视图、导入更新、`/api/scripts/maafw/*` 的大部分端点、启动期与每日维护 |
| `auto-mas-maafw-adapter` | `maafw_adapter` | 通用 MFW 专项（`MaaFWConfig`） |
| `auto-mas-m9a-adapter` | `m9a_adapter` | M9A 专项（`M9AConfig`） |
| `auto-mas-mss-adapter` | `mss_adapter` | MSS 专项（`MSSConfig`、`MSSPlanConfig`） |

专项按 pip 依赖带上积木和库：装 `auto-mas-maafw-adapter` 时五块积木一起装上，启用专项时宿主按 `requires` 先启用积木。托管、账号、计划表的类型名不变；托管属主名等于插件 ID，存量视图的属主标记由项目更新插件的维护循环补上。

## 升级时发生什么

数据版本已是 v2.2 的用户，启动时按下面的顺序走（`app/core/config/manager.py` 的 `check_data`）：

1. 扫 `scripts.yaml`、`ScriptConfig.json`、`plans.yaml`、`PlanConfig.json` 的类型索引，类型命中 `MaaFWConfig`、`M9AConfig`、`MSSConfig`、`MSSPlanConfig` 就记下要装的插件（`app/core/config/plugin_upgrade.py`）。
2. 首次接手前把这四个文件按字节备份到 `config/legacy-maafw-plugin/`；备份已存在就不覆盖，所以重试和后来的启动都不改写第一次的备份。
3. 装运行环境、加载已装插件，再逐个安装并启用要装的专项插件。
4. M9A 的受管任务整理（宿主自有，`app/core/config/m9a_legacy/`）在插件就绪之后、托管集合激活之前做；它要用解析库 `maafw_interface`，库不在就记一条说明跳过，下次启动再做。
5. 激活各配置集合。插件类在激活时兼容旧形状（`UserData` 转 `users`，`info.*` 从 `Info.*` 投影），宿主不写形状转换。
6. 初始化托管并 `flush`，这时第一次按插件形状写盘。
7. 项目更新插件启用后自己起维护：旧副本迁移、补属主标记、清副本、agent 与运行池对账。

数据版本更老的用户先按原有分段升级（`config/legacy-json/pre-upgrade/` 有整份备份），一次性的 M9A 旧版迁移也在这条路径上，同样要等插件装上、解析库可用才做。

## 插件装不上时

- 离线、PyPI 与镜像都不通、或插件启用失败：v2.2 用户的后端照常起来。对应的托管和计划表原样留在盘上（旁挂保留，`flush` 原样写回），列表里显示为「所属插件不可用」的只读卡片，只能删除；启动通知列出它们。队列项按 UID 引用托管，不会被改成「-」。下次启动再装。
- 数据版本早于 v2.2 时转换要靠插件在场，装不上时后台初始化失败（报「配置升级时有类型无法识别，所属插件不可用」），配置不写，版本号不推进，联网后重启再升。
- 没装插件时新建 MaaFW、M9A、MSS 托管会报出该装哪个包；`/api/scripts/maafw/*` 返回带说明的 404。
- 内置 MaaEnd 的游戏启动设置要用解析库 `maafw_interface`；没装 MFW 插件时这一步报错并提示安装。

## 宿主为插件 0.1.0 保留的东西

插件 0.1.0 仍直接导入一部分宿主模块，宿主暂不删除：`app/models/schema.py` 里的 MaaFW 模型与 `MSSPlanKey`、`app/core/ws/protocol.py` 的两个 MFW 进度常量、`app/core/notify/formats/maafw`、`normalize_mss_plan_key`、`app/core/config/manager.py` 的 `_PROCESS_STARTED_AT` 与 `Config.script_config_loaded_intact`、桌面分身执行器的 `maafw_windows` 动作。插件改走 SDK 出口之后再删。

## 回退

- 代码回退：revert 「MFW、M9A、MSS 改由插件提供，删除内置实现」那个提交，内置实现就回来了。
- 已经升级过的用户回到旧宿主：
  1. 关掉后端；
  2. 把 `config/legacy-maafw-plugin/` 下的文件拷回 `config/`；
  3. 在旧宿主里卸载 MFW 族插件（或不启用它们），再启动。
- 只回退代码、不还原备份时，旧宿主读不到 `users`，账号会显示为空。升级之后做的配置修改会随着还原备份一起丢失。
- 回退后再升级一次不会重新备份（备份已存在）；只要回退时按上面还原过，盘上就是旧形状，转换照常进行。

## 开发辅助

新发到 PyPI 的包当天可能不在数据站插件目录和 PyPI 的 simple 总索引里。起后端前设 `AUTO_MAS_PLUGIN_EXTRA_PACKAGES=auto-mas-maafw-adapter,auto-mas-m9a-adapter,auto-mas-mss-adapter`，刷新插件目录时会按包名从 PyPI 补进来。默认不设。
