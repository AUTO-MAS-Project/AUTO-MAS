import { expect, test } from './fixtures'
import { access } from 'node:fs/promises'
import path from 'node:path'

const backendUrl = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? '36174'}`
const dataRoot = process.env.AUTO_MAS_E2E_DATA_ROOT

test.describe('@init backend cold start', () => {
  test('reaches background ready with the optional Arknights PC toolkit disabled', async ({
    app,
    page,
  }, testInfo) => {
    const startedAt = performance.now()
    await app.goto('/home')

    let health: Record<string, unknown> = {}
    await expect
      .poll(
        async () => {
          const response = await page.request.get(`${backendUrl}/api/core/health`)
          if (!response.ok()) return 'unavailable'
          health = (await response.json()) as Record<string, unknown>
          return health.backgroundStatus
        },
        { timeout: 60_000, intervals: [250, 500, 1000, 2000] }
      )
      .toBe('ready')

    expect(health.ready).toBe(true)
    expect(health.backgroundError).toBeNull()
    const warnings = Array.isArray(health.backgroundWarnings)
      ? health.backgroundWarnings.map(String)
      : []
    expect(warnings.some(warning => warning.startsWith('明日方舟 PC 工具初始化'))).toBe(false)
    const toolsResponse = await page.request.post(`${backendUrl}/api/tools/get`)
    expect(toolsResponse.ok()).toBe(true)
    const tools = (await toolsResponse.json()) as {
      code?: number
      data?: { ArknightsPC?: { Enabled?: boolean } }
    }
    expect(tools.code).toBe(200)
    expect(tools.data?.ArknightsPC?.Enabled).toBe(false)

    expect(dataRoot).toBeTruthy()
    await expect
      .poll(
        async () => {
          try {
            await access(path.join(dataRoot!, 'config', 'maa_option.json'))
            return true
          } catch {
            return false
          }
        },
        { timeout: 5_000 }
      )
      .toBe(false)

    await testInfo.attach('backend-startup.json', {
      body: Buffer.from(
        JSON.stringify(
          {
            elapsedMs: Math.round(performance.now() - startedAt),
            ready: health.ready,
            backgroundStatus: health.backgroundStatus,
            backgroundWarnings: warnings,
            arknightsPcEnabled: tools.data?.ArknightsPC?.Enabled,
            maaOptionCreated: false,
          },
          null,
          2
        )
      ),
      contentType: 'application/json',
    })
  })
})
