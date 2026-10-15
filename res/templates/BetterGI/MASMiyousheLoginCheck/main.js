// 仅通过 BetterGI 公开接口读取角色 UID，不执行游戏任务或输入操作。
// https://github.com/babalae/bettergi-scripts-list/blob/main/bettergi.d.ts
(async function () {
  const runId = String(settings.runId || "");
  const expectedUid = String(settings.expectedUid || "");
  const marker = "MAS_MIYOUSHE_LOGIN:" + runId + ":";

  if (!/^[a-f0-9]{32}$/.test(runId) || !/^[1-9][0-9]*$/.test(expectedUid)) {
    log.info(marker + "UNAVAILABLE");
    return;
  }
  if (typeof genshin.uid !== "function") {
    log.info(marker + "UNAVAILABLE");
    return;
  }

  try {
    // 登录过渡帧可能尚未显示 UID；识别失败由上游返回 0。
    for (let attempt = 0; attempt < 20; attempt++) {
      const uid = await genshin.uid();
      if (uid > 0) {
        log.info(marker + (String(uid) === expectedUid ? "SUCCESS" : "MISMATCH"));
        return;
      }
      await sleep(500);
    }
  } catch (_) {
    // 只输出本次校验结果，不输出上游异常与游戏截图。
  }
  log.info(marker + "UNAVAILABLE");
})();
