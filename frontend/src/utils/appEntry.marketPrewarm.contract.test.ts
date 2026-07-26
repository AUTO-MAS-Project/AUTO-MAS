/**
 * appEntry 插件市场预热契约（源码级）：
 * - enterApp 与 forceEnterApp 进入应用后都触发 preloadPluginMarket；
 * - 预热通过动态 import 加载市场模块，不进启动关键路径；
 * - fire-and-forget：调用点不 await，失败仅记日志，不影响进入应用。
 *
 * 直接 import appEntry 会拉起 router/websocket 等真实依赖，故用源码断言。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(fileURLToPath(new URL('./appEntry.ts', import.meta.url)), 'utf8')

describe('appEntry plugin market prewarm wiring', () => {
  it('enterApp 与 forceEnterApp 都触发市场预热', () => {
    // 一处定义 + 至少两处调用（enterApp / forceEnterApp）
    const calls = source.match(/preloadPluginMarket\(reason\)/g) || []
    expect(calls.length).toBeGreaterThanOrEqual(2)
    expect(source).toMatch(/function preloadPluginMarket\(reason: string\): void/)
  })

  it('预热通过动态 import 加载市场模块且不被 await', () => {
    expect(source).toMatch(/void import\(['"]\.\.\/views\/plugin-market\/marketPrewarm['"]\)/)
    expect(source).toMatch(/prewarmPluginMarketSnapshot\(\)/)
    // 调用点必须 fire-and-forget，不允许 gate 启动流程
    expect(source).not.toMatch(/await preloadPluginMarket/)
  })

  it('预热失败静默：仅记录日志，不向上抛出', () => {
    expect(source).toMatch(
      /import\(['"]\.\.\/views\/plugin-market\/marketPrewarm['"]\)[\s\S]{0,400}\.catch\(/
    )
  })
})
