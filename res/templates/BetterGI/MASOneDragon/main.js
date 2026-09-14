// MASOneDragon/main.js
// 路径 B「MAS 自编排执行层」：读取 settings.plan.steps，按顺序把战斗 4 项直连
// BetterGI 原生任务（dispatcher.runAutoXxxTask）；日常 4 项不在此处理（由随后启动的
// 一条龙承接，其副本已过滤掉战斗 4 项，避免重复）。每步打印 MAS_STEP_* 标记行，
// 供 MAS 的 one_dragon_report 解析步骤级成败。
//
// ⚠️ 待实机复核（技术路径文档 #4/#5/#7）：
//   - settings 注入方式（全局 `settings` 还是脚本参数）、脚本入口约定；
//   - 地脉花 useAdventurerHandbook 语义反转（AutoPlan 记录需取反）；
//   - 秘境 domainRoundNum 轮数 ↔ 树脂次数的换算（已落地，见 dispatchCombat 自动秘境分支）；
//   - 字段名以目标版本 bettergi.d.ts 复核（本文件依据 bettergi-scripts-list 0.64 附近 d.ts）。

const COMBAT_STEPS = ["自动秘境", "自动地脉花", "自动幽境危战", "自动首领讨伐"];
const DAILY_STEPS = ["领取邮件", "合成树脂", "领取每日奖励", "领取尘歌壶奖励"];

// 执行层步骤命名约定：同一战斗类型可配多个独立实例，名字形如 "自动秘境-副本A"
// （基名 + "-" 后缀）。归一到基名以复用分发 / 每周逻辑。基名本身不含 "-"。
function baseStepName(name) {
  if (COMBAT_STEPS.includes(name) || DAILY_STEPS.includes(name)) return name;
  const idx = name.indexOf("-");
  return idx > 0 ? name.slice(0, idx) : name;
}

// 日志：优先 BGI 注入的 log（写入 BGI 日志文件，供 MAS 监控解析 MAS_STEP_* 标记），
// console.log 仅作兜底（不进日志文件）。不可命名回 log，避免遮蔽注入对象。
function masLog(line) {
  try {
    if (typeof log !== "undefined" && log && typeof log.info === "function") {
      log.info(line);
      return;
    }
  } catch (e) {
    /* 忽略注入缺失 */
  }
  console.log(line);
}

// 统一守卫：向 BGI Param 对象（.NET 互斥对象）赋值时，若该版本未暴露对应属性，
// 会抛 "no suitable property or field" 异常并中断整个执行层。setProp 静默跳过
// 不支持的属性并打标记，保证后续步骤继续执行。
function setProp(obj, name, value) {
  try {
    obj[name] = value;
  } catch (e) {
    masLog(
      "MAS_PROP_UNSUPPORTED: " + name + " " + ((e && (e.message || e.toString())) || String(e))
    );
  }
}

// 统一封装：每次 new 一个新 Param；必须 await；try/finally 复位主界面；
// 策略用 setCombatStrategyPath 的返回值回填（遵循 AutoPlan 六条纪律）。
// new Date().getDay() 的顺序：0=周日..6=周六
const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// 星期执行标记：地脉花的「执行」勾选由 MAS 托管在 weeklyLeyLine[day].run；
// 其余任务读扁平的 run{Day}。全部未勾选视为不限制（每天执行）。
function weekdayRunFlags(step) {
  const s = step.settings || {};
  const weekly = s.weeklyLeyLine;
  if (weekly && typeof weekly === "object") {
    const flags = DAY_NAMES.map((d) => !!(weekly[d] && weekly[d].run === true));
    if (flags.some(Boolean)) return flags;
  }
  return DAY_NAMES.map((d) => s["run" + d] === true);
}

// 星期编排：仅当勾选的星期包含今天才执行；全部未勾选视为不限制（每天执行）。
// 由 MAS 自行管理，不依赖被过滤掉的原生一条龙「每周刷取」配置表。
function shouldRunToday(step) {
  const s = step.settings || {};
  // 秘境特殊处理：每周秘境开启时按当天的「执行」开关（开启才执行）；全关=不执行。
  // 每日秘境（关闭每周）不受星期限制，每天都跑。
  if (baseStepName(step.name) === "自动秘境") {
    const useWeekly = s.weeklyDomainEnabled !== false;
    if (useWeekly) {
      const wd = s.weeklyDomain || {};
      const wdName = DAY_NAMES[new Date().getDay()];
      return !!(wd[wdName] && wd[wdName].run === true);
    }
    return true;
  }
  const flags = weekdayRunFlags(step);
  if (!flags.some(Boolean)) return true;
  return flags[new Date().getDay()];
}

// 树脂耗尽是用户开启「树脂耗尽模式」后的预期停止条件：BGI 抛
// System.Exception「树脂耗尽，任务结束」（AutoLeyLineOutcropTask.cs:120），
// 属正常收尾而非失败。识别它以免中断整个执行层、连坐后续步骤。
function isResinExhausted(msg) {
  const s = String(msg || "");
  return s.indexOf("树脂耗尽") >= 0 || s.indexOf("树脂不足") >= 0;
}

async function dispatchCombat(step) {
  const s = step.settings || {};
  switch (baseStepName(step.name)) {
    case "自动秘境": {
      // 每周配置由 MAS 托管：按今天星期从 settings.weeklyDomain 取对应行（回退 default）。
      // 关闭「每周秘境」时只走每日行；奖励档位同理，每周走 default.reward（每周表默认行），
      // 走每日则用 sundaySelectedValue（每日行），两者不可混用。
      const wdName = DAY_NAMES[new Date().getDay()];
      const wd = s.weeklyDomain || {};
      const defaultRow = wd.default || {};
      const useWeekly = s.weeklyDomainEnabled !== false;
      const todayRow = (useWeekly && wd[wdName]) || {};
      const partyName = todayRow.partyName || defaultRow.partyName || s.partyName;
      const domainName = todayRow.domainName || defaultRow.domainName || s.domainName;
      const reward = useWeekly
        ? todayRow.reward != null
          ? todayRow.reward
          : defaultRow.reward != null
            ? defaultRow.reward
            : s.sundaySelectedValue
        : s.sundaySelectedValue;
      // 战斗策略：优先当天行，其次每周默认行，最后才是步骤级 combatStrategyPath（全局兜底）。
      // 留空则完全不设置，由 BGI 沿用 autoFightConfig 的全局策略。
      const strategyName = todayRow.strategy || defaultRow.strategy || s.combatStrategyPath;
      // 今天无对应秘境配置则跳过（不执行）
      if (!domainName) {
        masLog("MAS_STEP_SKIP_WEEKDAY: " + step.uid + " " + step.name);
        return;
      }
      // 轮数换算（原文件头 TODO #7）：前端右栏不暴露 domainRoundNum，直接取默认值 1
      // 会让 BGI 的 AutoDomain 只刷 1 轮就「正常返回」（不抛异常）——表现为第二轮角色
      // 一动不动、攒够超时后反复 ESC 回主界面、最后被 MAS 记成 MAS_STEP_DONE 成功。
      // 这里按「指定树脂刷取次数」求和换算轮数：浓缩/须臾/脆弱/原粹每次各计 1 轮。
      const resinRounds =
        (s.condensedResinUseCount || 0) +
        (s.transientResinUseCount || 0) +
        (s.fragileResinUseCount || 0) +
        (s.originalResinUseCount || 0);
      // settings 经 JSON 注入/回读，布尔可能以字符串形态出现；这里只规范化一次，
      // 并把这个结果同时用于「模式判断」与下面的 Param 透传，避免两处得出相反结论
      // （例如字符串 "false" 会被 !! 转成 true，BGI 就会收到
      // 「模式=树脂耗尽 / 参数=指定次数」的矛盾设置）。
      const specifyResinUse = s.specifyResinUse === true || s.specifyResinUse === "true";
      let roundNum;
      if (specifyResinUse) {
        // 指定次数模式：轮数 = 各树脂次数之和；次数全为 0 时回退步骤级配置
        roundNum = resinRounds > 0 ? resinRounds : s.domainRoundNum != null ? s.domainRoundNum : 1;
      } else {
        // 耗尽模式：不设轮数上界，由 BGI 在体力耗尽时自行正常结束
        // （实测收尾行「体力耗尽或者设置轮次已达标，结束自动秘境」，不抛异常）。
        // 不回退 s.domainRoundNum：耗尽模式与「限定轮数」互斥，该键前端从不产出，
        // 回退只会让残留它的旧设置被意外截断。
        roundNum = 999;
      }
      const p = new AutoDomainParam(roundNum);
      if (partyName) p.partyName = partyName;
      if (domainName) p.domainName = domainName;
      if (reward != null) p.sundaySelectedValue = String(reward);
      if (s.autoArtifactSalvage != null) p.autoArtifactSalvage = !!s.autoArtifactSalvage;
      if (s.maxArtifactStar != null) p.maxArtifactStar = String(s.maxArtifactStar);
      // 用上面规范化后的值，确保与轮数换算取到同一个模式
      if (s.specifyResinUse != null) p.specifyResinUse = specifyResinUse;
      if (s.originalResinUseCount != null) p.originalResinUseCount = s.originalResinUseCount;
      if (s.condensedResinUseCount != null) p.condensedResinUseCount = s.condensedResinUseCount;
      if (s.transientResinUseCount != null) p.transientResinUseCount = s.transientResinUseCount;
      if (s.fragileResinUseCount != null) p.fragileResinUseCount = s.fragileResinUseCount;
      if (strategyName) p.combatStrategyPath = p.setCombatStrategyPath(strategyName);
      if (Array.isArray(s.resinPriorityList)) p.setResinPriorityList(...s.resinPriorityList);
      await genshin.returnMainUi();
      try {
        await dispatcher.runAutoDomainTask(p);
      } finally {
        await genshin.returnMainUi();
      }
      break;
    }
    case "自动地脉花": {
      // 每日地脉花（leyLineDailyEnabled）优先于每周地脉花：开启时走每日统一配置，直接执行；
      // 否则走每周地脉花：按今天星期取对应行，仅当该行执行开关开启才刷取，
      // 当天某字段为空时按「默认」行兜底（默认行无执行开关）。
      const wdName = DAY_NAMES[new Date().getDay()];
      // 未配置（新用户）默认走每日模式，与右栏「开启每日地脉花」默认开启一致；
      // 仅显式 false（用户选了每周地脉花）才走每周分支。
      const daily = s.leyLineDailyEnabled !== false;
      let country, leyLineOutcropType, team, strategy;
      if (daily) {
        country = s.country;
        leyLineOutcropType = s.leyLineOutcropType;
        team = s.team;
        strategy = s.combatStrategyPath;
      } else {
        const weeklyLeyLine = s.weeklyLeyLine || {};
        const wdRow = weeklyLeyLine[wdName] || {};
        // 执行开关全部关闭（今天的行未勾选）即不执行
        if (wdRow.run !== true) {
          masLog("MAS_STEP_SKIP_WEEKDAY: " + step.uid + " " + step.name);
          break;
        }
        const def = weeklyLeyLine.default || {};
        country = wdRow.country != null ? wdRow.country : (def.country != null ? def.country : s.country);
        leyLineOutcropType = wdRow.type != null ? wdRow.type : (def.type != null ? def.type : s.leyLineOutcropType);
        team = wdRow.team || def.team || s.team;
        strategy = wdRow.strategy || def.strategy || s.combatStrategyPath;
      }
      const p = new AutoLeyLineOutcropParam(
        s.count != null ? s.count : 3,
        country || "",
        leyLineOutcropType || ""
      );
      if (s.isResinExhaustionMode != null) p.isResinExhaustionMode = !!s.isResinExhaustionMode;
      if (s.openModeCountMin != null) p.openModeCountMin = !!s.openModeCountMin;
      // 前端「不使用冒险之证寻路」勾选=true 表示不通过冒险之证，与 BGI Param 的
      // useAdventurerHandbook 语义相反，此处取反后透传（原 TODO(#4) 已据 UI 语义落地）。
      if (s.useAdventurerHandbook != null) p.useAdventurerHandbook = !s.useAdventurerHandbook;
      // 「跳过准备流程」(LeyLineOneDragonMode) 因 BGI 未向 JS 暴露注入点，在 MAS 接管路径
      // 下无效，已从右栏移除；此处不再消费该键（如将来 BGI 提供注入点可在此补回）。
      // 地脉花无原生超时，不兜底（前端默认 0=不限制）；仅当显式 >0 时透传。
      if (s.timeout != null && s.timeout > 0) p.timeout = s.timeout;
      if (s.useFragileResin != null) p.useFragileResin = !!s.useFragileResin;
      if (s.useTransientResin != null) p.useTransientResin = !!s.useTransientResin;
      // 好感队仅在战斗队伍填写后才透传（冻结态视为空）
      if (team) p.team = team;
      if (team && s.friendshipTeam) p.friendshipTeam = s.friendshipTeam;
      // 地脉花 Param 在部分 BGI 版本无 setCombatStrategyPath（d.ts 未声明），做存在性守卫防 TypeError
      if (strategy) {
        if (typeof p.setCombatStrategyPath === "function") {
          p.combatStrategyPath = p.setCombatStrategyPath(strategy);
        } else {
          masLog("MAS_LEYLINE_STRATEGY_UNSUPPORTED: " + strategy);
        }
      }
      await genshin.returnMainUi();
      try {
        await dispatcher.runAutoLeyLineOutcropTask(p);
      } finally {
        await genshin.returnMainUi();
      }
      break;
    }
    case "自动幽境危战": {
      // 无参构造：SetDefault() 先把 BGI 全局幽境配置（含默认策略路径）填进 Param。
      // 不要用 AutoStygianOnslaughtParam("")——带参构造会用空串覆盖 CombatScriptBagPath，
      // 导致未指定策略时丢掉全局默认策略（源码 AutoStygianOnslaughtParam.cs 已核实）。
      const p = new AutoStygianOnslaughtParam();
      // BGI 部分版本未在 Param 类上暴露某些属性（如 AutoStygianOnslaughtParam 无
      // maxArtifactStar），直接赋值会抛 "no suitable property or field" 并中断整个
      // 执行层（实机 0.64.1-alpha.1 已复现）。统一走 setProp 静默跳过并打标记。
      if (s.bossNum != null) setProp(p, "bossNum", s.bossNum);
      if (s.autoArtifactSalvage != null) setProp(p, "autoArtifactSalvage", !!s.autoArtifactSalvage);
      if (s.specifyResinUse != null) setProp(p, "specifyResinUse", !!s.specifyResinUse);
      if (s.originalResinUseCount != null) setProp(p, "originalResinUseCount", s.originalResinUseCount);
      if (s.condensedResinUseCount != null) setProp(p, "condensedResinUseCount", s.condensedResinUseCount);
      if (s.transientResinUseCount != null) setProp(p, "transientResinUseCount", s.transientResinUseCount);
      if (s.fragileResinUseCount != null) setProp(p, "fragileResinUseCount", s.fragileResinUseCount);
      // 右栏幽境面板的战斗队伍/策略优先（fightTeamName/strategyName 来自 globalStygian），
      // 留空时 Param 不设置，BGI 回退全局 config.json 段（顶部通用队伍/策略兜底）。
      if (s.fightTeamName) setProp(p, "fightTeamName", s.fightTeamName);
      const stygianStrategy = s.strategyName || s.combatStrategyPath;
      // 幽境 Param 无 combatStrategyPath 属性：setCombatStrategyPath(strategyName) 有副作用，
      // 内部把 "User\AutoFight\<策略名>.txt" 写入 CombatScriptBagPath（源码已核实）。
      // 只调用方法本身即可，不要把返回值赋给属性（会抛 no suitable property 异常）。
      if (stygianStrategy) {
        if (typeof p.setCombatStrategyPath === "function") {
          p.setCombatStrategyPath(stygianStrategy);
        } else {
          masLog("MAS_STYGIAN_STRATEGY_UNSUPPORTED: " + stygianStrategy);
        }
      }
      if (Array.isArray(s.resinPriorityList)) p.setResinPriorityList(...s.resinPriorityList);
      await genshin.returnMainUi();
      try {
        await dispatcher.runAutoStygianOnslaughtTask(p);
      } finally {
        await genshin.returnMainUi();
      }
      break;
    }
    case "自动首领讨伐": {
      // ⚠️ 不能用 new SoloTask("AutoBoss", cfg)：官方文档（dev/js/dispatcher.html）
      // 明确 AutoBoss 是「基础任务（无配置参数）」，SoloTask 第二参会被整体忽略——
      // 配置从未进入 AutoBossParam，Validate() 见 BossName 为空恒抛
      // 「请选择需要讨伐的首领」（2026-09-10 实机日志定位，bossName 落盘正常仍报错）。
      // 正确通道：new AutoBossParam()（无参=SetDefault 读本体配置）+ 逐字段覆盖
      // + dispatcher.runAutoBossTask(param)。属性赋值统一走 setProp，兼容未暴露属性。
      const p = new AutoBossParam();
      // bossName 必填（Validate 第一道校验）；Param 无参构造已读本体配置作兜底
      if (s.bossName) setProp(p, "bossName", s.bossName);
      if (s.teamName) setProp(p, "teamName", s.teamName);
      if (s.specifyRunCount != null) setProp(p, "specifyRunCount", !!s.specifyRunCount);
      if (s.runCount != null) setProp(p, "runCount", s.runCount);
      if (s.useTransientResin != null) setProp(p, "useTransientResin", !!s.useTransientResin);
      if (s.useFragileResin != null) setProp(p, "useFragileResin", !!s.useFragileResin);
      // Plan 存量键为 rviveRetryCount（后端 RIGHTBAR_TO_PLAN 历史拼写），新键 reviveRetryCount 兼容
      const reviveRetry = s.rviveRetryCount != null ? s.rviveRetryCount : s.reviveRetryCount;
      if (reviveRetry != null) setProp(p, "reviveRetryCount", reviveRetry);
      if (s.returnToStatueAfterEachRound != null) setProp(p, "returnToStatueAfterEachRound", !!s.returnToStatueAfterEachRound);
      if (s.rewardRecognitionEnabled != null) setProp(p, "rewardRecognitionEnabled", !!s.rewardRecognitionEnabled);
      if (s.timeout != null) setProp(p, "timeout", s.timeout);
      // 首领讨伐策略存于 s.strategyName（由右栏 AutoBossStrategyName 映射而来）；
      // 其余组策略走 s.combatStrategyPath。两者取其一经 setCombatStrategyPath 按策略名重算路径。
      const bossStrategy = s.strategyName || s.combatStrategyPath;
      if (bossStrategy && typeof p.setCombatStrategyPath === "function") {
        p.setCombatStrategyPath(bossStrategy);
      }
      await genshin.returnMainUi();
      try {
        await dispatcher.runAutoBossTask(p);
      } finally {
        await genshin.returnMainUi();
      }
      break;
    }
  }
}

function safeParsePlan(raw) {
  if (typeof raw === "string" && raw.trim()) {
    try {
      return JSON.parse(raw);
    } catch (e) {
      return { version: 1, steps: [] };
    }
  }
  return raw;
}

async function main() {
  masLog(
    "MAS_SETTINGS_KEYS " +
      (typeof settings !== "undefined" && settings
        ? Object.keys(settings).join(",")
        : "(no settings)")
  );
  const rawPlan =
    typeof settings !== "undefined" && settings ? settings.plan : undefined;
  const plan = safeParsePlan(rawPlan) || {
    version: 1,
    steps: [],
  };
  const steps = Array.isArray(plan.steps) ? plan.steps : [];
  masLog("MAS_PLAN_BEGIN " + steps.length);
  // 单步失败计数：识别类异常（如大地图特征点匹配失败）不应中断整个编排，
  // 记录后跳过该步、继续后续步骤，结束时以 MAS_PLAN_DONE_WITH_FAILURES 汇总
  // （2026-09-09 用户决策）。
  let failed = 0;
  for (const step of steps) {
    if (!step || !step.enabled) {
      masLog("MAS_STEP_SKIP: " + (step ? step.uid : "?"));
      continue;
    }
    if (DAILY_STEPS.includes(baseStepName(step.name))) {
      masLog("MAS_STEP_DAILY: " + step.uid + " " + step.name); // 由随后的一条龙承接
      continue;
    }
    if (!COMBAT_STEPS.includes(baseStepName(step.name))) {
      masLog("MAS_STEP_UNKNOWN: " + step.uid + " " + step.name);
      continue;
    }
    if (!shouldRunToday(step)) {
      masLog("MAS_STEP_SKIP_WEEKDAY: " + step.uid + " " + step.name);
      continue;
    }
    masLog("MAS_STEP_BEGIN: " + step.uid + " " + step.name);
    try {
      await dispatchCombat(step);
      masLog("MAS_STEP_DONE: " + step.uid + " " + step.name);
    } catch (e) {
      const msg = (e && (e.message || e.toString())) || String(e);
      // 树脂耗尽是用户开启「树脂耗尽模式」后的预期停止条件：BGI 抛
      // System.Exception「树脂耗尽，任务结束」（AutoLeyLineOutcropTask.cs:120），
      // 属正常收尾而非失败。按正常结束处理，避免中断整个执行层并把后续步骤连坐。
      if (isResinExhausted(msg)) {
        masLog("MAS_STEP_RESIN_END: " + step.uid + " " + step.name + " " + msg);
        masLog("MAS_PLAN_RESIN_END");
        masLog("MAS_PLAN_DONE");
        return;
      }
      failed++;
      masLog("MAS_STEP_FAIL: " + step.uid + " " + step.name + " " + msg);
      // 不再 throw：单个步骤失败只跳过该步，继续后续步骤
      continue;
    }
  }
  masLog(failed > 0 ? "MAS_PLAN_DONE_WITH_FAILURES " + failed : "MAS_PLAN_DONE");
}

main().catch((e) => {
  const msg = (e && (e.message || e.toString())) || String(e);
  masLog("MAS_PLAN_FAIL " + msg);
  throw e;
});
