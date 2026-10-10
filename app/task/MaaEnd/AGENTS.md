# `app/task/MaaEnd` 说明

本文件只记录代码里读不出来、但改错了会出事的约束。

## 终末地 PC 客户端更新（先行补位）

- `tools/game_update.py` 直接写游戏安装目录。按
  `.agents/skills/mas-script-specialized-adapter/references/blackbox-boundary.md`
  「直接操作游戏本体一律属上游领域」这是**先行补位**：本专项此前没有可编程的更新入口。
  出现同能力入口后改为复用，并一并删掉这些：`tools/game_update.py` 与
  `tools/package_index.py`、`MaaEndManager._ensure_game_client_updated` 和它按 `"Update"`
  模式分流的那几处分支、`MaaEnd/Update.py` 的手动任务、脚本页那颗「检查更新」按钮与它的
  `useMaaEndUpdate.ts`、`Game.IfAutoUpdate` 与 `Game.UpdateTimeLimit` 两个配置字段、
  `app/utils/constants.py` 的 `ENDFIELD_SERVER_PRESETS`。
- 任务启动前的自动门与脚本页手动入口**共用同一条判定链** `ensure_game_updated()`，
  不是并存的两套语义；区别只在状态用法——自动门对「判不了」放行 `Skipped`，手动入口要把
  它如实说成没查出结论。门挂在 `main_task` 里，因此 AutoProxy 下所选账号全部命中维护
  窗口时基类直接收尾、门整轮不跑（本轮不检查客户端更新，维护结束后首轮恢复）；这是已知
  边界，别把它当成漏播去把门往前挪。
- `config.ini` 只读、绝不写回：新版本号只用差量包内自带的那份覆盖，并且它是本轮最后一次
  改名提交。改了这个顺序，就没有「更新到底生效了没有」的判据了。
- `Update.py` 更新的是**游戏客户端**；`update_takeover.py` 接管的是 MaaEnd 程序自身的更新，
  两件事，别合并。
- 第三方许可与来源声明见 `tools/LICENSE.HypergryphPlugin.md`：本模块按 Hi3Helper.Plugin.Hypergryph
  （MIT）公开源码描述的流程与协议重写，打包与再分发时必须随代码一起带上那份声明。
