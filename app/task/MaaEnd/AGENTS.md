# `app/task/MaaEnd` 说明

本文件只记录代码里读不出来、但改错了会出事的约束。

## 终末地 PC 客户端更新（先行补位）

- `tools/update/` 的更新实现直接写游戏安装目录。按
  `.agents/skills/mas-script-specialized-adapter/references/blackbox-boundary.md`
  「直接操作游戏本体一律属上游领域」这是**先行补位**：本专项此前没有可编程的更新入口。
  出现同能力入口后改为复用，并一并删掉这些：`tools/update/`、`MaaEndManager._ensure_game_client_updated` 和它按 `"Update"`
  模式分流的那几处分支、`MaaEnd/Update.py` 的手动任务、脚本页那颗「检查更新」按钮与它的
  `useMaaEndUpdate.ts`、`Game.IfAutoUpdate` 与 `Game.UpdateTimeLimit` 两个配置字段、
  `app/utils/constants.py` 的 `ENDFIELD_SERVER_PRESETS`。
- 任务启动前的自动门与脚本页手动入口**共用同一条判定链** `ensure_game_updated()`，
  不是并存的两套语义；区别只在状态用法——自动门对「判不了」放行 `Skipped`，手动入口要把
  它如实说成没查出结论。门挂在 `main_task` 里，因此 AutoProxy 下所选账号全部命中维护
  窗口时基类直接收尾、门整轮不跑（本轮不检查客户端更新，维护结束后首轮恢复）；这是已知
  边界，别把它当成漏播去把门往前挪。
- `config.ini` 只读、绝不写回：新版本号只用差量包内自带的那份覆盖，并且它是本轮最后一次
  改名提交。改了这个顺序，就没有「更新到底生效了没有」的判据了——它同时是「本轮完成」
  的唯一判据：收尾按安装目录里的版本号是不是目标版本，决定清掉暂存还是留给下一轮续传。
- **下载与落盘都跨轮续传**：暂存目录 `_mas_endfield_update/` 里的分卷、目标旁的 `.mas-part`
  临时文件、以及已经改名就位的文件都留着，下一轮接着下、接着写。判据是各阶段自己的指纹：
  分卷比体积与 MD5，落地条目比**新文件**的体积与 MD5（`_check_baselines` 先看目标位置是不是
  已经是新值再去看旧基线；只认旧基线会把上一轮的成果判成「与官方不符」，用户就永远停在手动
  更新上）。`_mas_endfield_update/state.json` 是续传的唯一事实来源，缺它、坏它、或它的目标
  版本/分卷指纹与本轮不符，一律按没有暂存处理。
- 只有三种情况才把暂存整个清掉：本轮完成、服务端换了目标版本或差量指纹、以及超过
  `_STAGING_RETENTION_SECONDS`（14 天）没动过。其余情况（取消、超时、失败、门禁拦住）
  一律保留。`state.json` 的 `landing_started` 只在**第一次写盘之前**置位：下载与核对阶段
  一个字都没写进游戏目录，那时置位会让下一轮把「什么都没动过」误判成「半新半旧」。
- 已经动过游戏目录（`landing_started`）而本轮取不到版本信息（断网等）时必须走
  `NeedManualUpdate` 阻断，不能对 `Skipped` 放行——客户端可能停在半新半旧，放行等于让脚本
  跑在坏客户端上。没动过客户端时仍按 `Skipped` 放行，别把探测失败算到用户任务头上。
- `Update.py` 更新的是**游戏客户端**；`update_takeover.py` 接管的是 MaaEnd 程序自身的更新，
  两件事，别合并。
- 第三方许可与来源声明见 `tools/update/LICENSE.HypergryphPlugin.md`：本模块按 Hi3Helper.Plugin.Hypergryph
  （MIT）公开源码描述的流程与协议重写，打包与再分发时必须随代码一起带上那份声明。
