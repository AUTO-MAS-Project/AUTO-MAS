# 案例：M9A（已不是专项）

M9A 已并入 MFW（#973）：它是 **MaaFW 通用引擎的特调类型**，不再有自己的任务目录、编辑页、
队列 JSON 或 restore_service。原先本文记录的 MFAA 线专项实现（`M9AUserEdit`、任务队列、
纯字段侧车）已随代码删除，不要照着去找或复刻。

- 现状与边界：`app/task/M9A/AGENTS.md`（特调只经 `FLAVOR` 钩子进入，`flavor.py` 加首尾任务与切号，
  `migration.py` 把旧专项配置一次性迁成 MaaFW 形状）；运行、更新、通知、周期任务全部是
  `app/task/MaaFW/AGENTS.md` 的既有语义。
- 配置备份恢复：走 [config-restore.md](config-restore.md) 的 MaaFW 分支。
- 新接入的 `interface.json` 项目（含外置 GUI 是 MFAAvalonia 的）先用通用 `MaaFW` 类型；所有 MaaFW
  项目都该有的做进引擎，只属于某个项目的才问用户值不值得加一条特调，定线判据见
  [script-frontend-architectures.md](script-frontend-architectures.md)。
