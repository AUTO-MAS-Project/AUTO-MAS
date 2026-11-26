# 案例：ZzzOd（绝区零 / zzz-od）

ZzzOd 属 `one-dragon` 家族，账号配置以 `ZzzOdUserConfig` 字段为事实源，运行时物化注入绑定实例槽（`config/{idx:02d}`）；具体路径与函数名现场读 `app/task/ZzzOd/`。

## 一、核心架构约束

- **零侵入边界**：MAS **零 import、零执行、零修改**一条龙源码。仅允许：① 读写实例 YAML；② 正则静态解析 `*_const.py` / `agent.py`；③ 读 `assets/game_data/*.yml`；④ CLI 拉起官方启动器。
- **配置来源与切换模式**：
  - 界面提供「独立 / 原生」（禁用共享，无独立覆写开关，`IfQuickConfig` 归一为关）。兼容值 `shared` 按当前账号字段注入绑定槽；原生来源直接编辑原生 YAML 并 `--onedragon` 裸跑零注入。
  - `Game.AccountSwitch`：默认**单实例切换**（manager 每次只 spawn 一个代理，失败域隔离最好）；**多实例切换**（`--onedragon --instance s1,s2,...`，仅 `instance_run=全部实例` 生效）；**MAS 账号切换**（预留，选它直接提示暂未开放）。
- **游戏进程与结束动作**：`CloseOnFinish` 按进程名兜底结束 `ZenlessZoneZero.exe`；`OneDragon.AfterDone` 由 MAS 接管（关闭游戏传 `--close-game`，关机由 MAS 在全部参与账号成功且全部槽恢复完成后安排 60 秒倒计时，任一槽恢复失败取消关机）。

## 二、高频反模式与真实事故解读（必读）

| ❌ 错误做法（反模式） | 💥 会导致什么真实事故 | ✅ 正确做法 |
| --- | --- | --- |
| 把 MAS 槽持久写入 `one_dragon.yml` 注册表 | MAS 实例混进用户原生 GUI、跨托管槽串号、「仅运行当前」误跑原生账号 | **注册表零持久写入**：窗口内用 `write_instance_view` 写入合成视图，结束 `restore_instance_view` 还原（崩溃靠 `.mas-view.bak` 自愈） |
| 照搬 MAA 把整个 `config/` 按账号复制 N 份 | N 倍体积膨胀、破坏跨槽配队引用、且一条龙不支持跨多棵树跑多账号 | 坚持「`UserData` 字段 + 绑定高位槽 `[1001, 9999]` 物化」两半合一 |
| 单看盘上 `config/NN` 目录就把“持久绑定查不到”的槽当孤儿回收 | 一条龙新建实例是先建目录后写注册表，且崩溃会留下未回写绑定号的在用槽，**直接误删用户正在建的实例或配队** | 仅按台账 `data/ZzzOdSlots/{指纹}.json` 白名单自动回收（**只收归属账号已不存在的号**，归属未知一律保留）；撞号时存底进回收池不删目录 + 改绑高位槽 |
| 回收池恢复直接写到裸槽号（不绑定账号） | 无绑定槽 MAS 永远不认领，新账号也不会认领，恢复完等于丢进黑洞 | 必须落到现有或新建账号的绑定槽（新建复用宿主 `add_user`，恢复失败撤回新建账号） |
| 角色下拉只读 `assets/game_data/agent/*.yml`，或正则只匹配单引号单行 | 新角色（如 yixuan/sunna）不在旧数据文件里，且新源码用双引号多行，**下拉漏掉所有新角色** | 正则解析 `src/zzz_od/game_data/agent.py` 的 `AgentEnum`，使用 `Agent\(\s*['"]([\w]+)['"],\s*['"]([^'"]+)['"]`，数据文件仅兜底 |
| 配置会话只注入不回读，或回读时无条件覆盖空账号/密码 | 不回读导致用户在 GUI 的修改下次运行被 MAS 覆盖；空值回读会破坏「留空沿用登录态」语义 | 打开前 `inject_user_fields`、关闭时 `_readback_user_fields`（账号/密码非空才回读）；`viewOnly` 查看会话不注入也不回读 |
| 直接给 `ScriptItem.result` 赋值，或未先物化槽就直接快照 mas 池 | `ScriptItem.result` 是只读计算属性直接抛 `AttributeError`；未物化直接快照会漏掉 `UserData` 里的账号/编排，恢复等于清空 | 报告正文用 `build_user_result_text` 局部变量；mas 槽快照统一走 `archive_mas_config_backup`（先物化再快照） |
| 把 `instance_run` 挂在 `native-config/save`（耦合所选实例） | 未选中实例时全局「运行实例」下拉被置灰且存不了 | `instance_run` 走独立端点 `instances/run-mode`；原生来源校验前先 `restore_instance_view` 自愈，用 `instance_run_is_all` 区分键缺失与 `null` |
| 在 OpenAPI 路由用中文 `Literal`，或路由路径互为前缀（如 `/active` 与 `/active-in-od`） | `openapi-typescript-codegen` 生成重复 `_` 标识符导致 TS 编译失败，或**静默丢弃前缀重叠端点** | 枚举放后端白名单校验（schema 用 `str`）；路径避开互为前缀（用 `set-active`）；必须在 `frontend/` 目录运行生成 |
| 把「指令[ 一条龙 ] 执行成功」当全部应用成功，或把「通知」应用失败触发重跑 | 吞掉单个应用失败，或把 3 小时汇总通知当本轮失败反复无意义重跑 | 逐应用取终态日志/运行记录差分；「通知」应用失败不触发重跑；吞失败警告由 `push_log.py` 白名单追加 `⚠ 异常:` |
