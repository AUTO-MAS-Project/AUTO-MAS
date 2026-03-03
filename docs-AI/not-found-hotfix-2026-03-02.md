# 启动即 Not Found 问题排查与最小修复（2026-03-02）

## 结论
- 正常提交：`8dc4612c15c4e5da74814c5e83543353897f6559`
- 首次出现问题：`7d7ffeac7f43ea96d85c812c380f27b5f13c3651`
- 逐条回滚验证后，致因文件为：`frontend/src/composables/useAppInitialization.ts`

## 根因
`useAppInitialization.ts` 在该区间引入了“持久化初始化状态（布尔值）”读取逻辑。启动时若读取到历史 `true`，初始化页会直接跳过流程并进入应用；此时后端初始化链路可能尚未完成，前端接口请求出现 `Not Found`。

## 已验证的最小修复
仅对 `frontend/src/composables/useAppInitialization.ts` 进行回退（恢复为内存态初始化标记，不在启动时直接信任持久化布尔值），问题消失。

## 推荐修复策略（后续可演进）
1. 短期热修：保持最小回退（已验证有效）。
2. 中期方案：如需保留持久化，改为“版本号标记 + 启动校验”组合判定：
   - 持久化版本号与当前前端版本号一致；
   - 后端可启动且关键资源可用；
   - 校验失败时强制走初始化流程。

## 过程记录
- 已撤销一次错误历史重排（rebase），将 `feat/InitMark` 恢复到 `6b7ce89d`（与 `origin/feat/InitMark` 对齐）。
- 测试时产生的临时工作区改动已入 stash：`temp-before-undo-rebase-20260302`。
