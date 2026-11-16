import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './fixtures'
import { observeMainConnection } from './socket-recovery'
import { projectTaskTree } from '../src/composables/taskTreeProjection'
import type { TaskItemDocument } from '../src/api'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const dailyFiles = ['DailyRoutineTask.json', 'DailyRoutineTaskConfigs.json']
test.use({
  video: 'off',
  launchOptions: { executablePath: process.env.AUTO_MAS_E2E_CHROMIUM_PATH },
})

test.describe('@real @oknte-plan-real', () => {
  test.skip(process.env.AUTO_MAS_E2E_REAL !== '1', '需要本机真实运行环境')
  test('daily overrides reach the real script and restore account configuration', async ({
    app,
    page,
  }, testInfo) => {
    test.setTimeout(45 * 60 * 1000)
    const scriptId = process.env.AUTO_MAS_E2E_SCRIPT_ID!
    const userId = process.env.AUTO_MAS_E2E_USER_ID!
    const accountName = process.env.AUTO_MAS_E2E_ACCOUNT_NAME!
    const post = async (endpoint: string, data: unknown) => {
      const response = await page.request.post(`${backend}${endpoint}`, { data })
      expect(response.ok()).toBe(true)
      const body = await response.json()
      expect(body.code, body.message).toBe(200)
      return body
    }
    let taskId: string | undefined
    let completion: { outcome: string; task: TaskItemDocument } | undefined
    let injected = false
    let restored = false
    let finalStatus = 'not-started'
    await observeMainConnection(page, payload => {
      const message = JSON.parse(payload.toString())
      if (message.type === 'task.completed' && message.id === taskId) completion = message.data
    })
    await app.goto('/scheduler')
    const scripts = (await post('/api/scripts/get', { scriptId })).data
    const script = scripts[scriptId]
    expect(script.Info.Name).toBe('nte计划任务')
    const users = (await post('/api/scripts/user/get', { scriptId })).data
    expect(Object.keys(users)).toEqual([userId])
    expect(users[userId].Info.Name).toBe(accountName)
    const configDir = script.Script.ConfigPath as string
    const quickDir = path.join(
      process.env.AUTO_MAS_E2E_DATA_ROOT!,
      'data',
      scriptId,
      userId,
      'QuickConfig'
    )
    const nativeBefore = await Promise.all(
      dailyFiles.map(file => readFile(path.join(configDir, file), 'utf8'))
    )
    const quickBefore = await Promise.all(
      dailyFiles.map(file => readFile(path.join(quickDir, file), 'utf8'))
    )
    const base = JSON.parse(quickBefore[1])
    const planId = (await post('/api/plan/add', { type: 'OkNtePlan' })).planId
    const day = new Intl.DateTimeFormat('en-US', { weekday: 'long', timeZone: 'Etc/GMT+4' }).format(
      new Date()
    )
    await post('/api/plan/update', { planId, data: { Info: { Mode: 'Weekly' } } })
    const patch = {
      'DailyRoutineTask.json': {
        'Routine Items': [
          { id: 'daily_anomaly', enabled: true },
          { id: 'daily_anomaly_hunter', enabled: false },
          ...['coffee', 'cinema_date', 'fountain', 'furniture', 'gift'].map(id => ({
            id,
            enabled: false,
          })),
        ],
      },
      'DailyRoutineTaskConfigs.json': {
        daily_anomaly: { 目标消耗体力: 200, 任务类型: '经验与甲硬币', 具体奖励目标: '角色经验' },
      },
    }
    await post('/api/scripts/oknte/plan/save', {
      plan_id: planId,
      day,
      configs: patch,
      replace: true,
    })
    await post('/api/scripts/user/update', {
      scriptId,
      userId,
      data: { Info: { PlanMode: planId } },
    })
    await app.goto(`/plans?planId=${planId}`)
    await app.evidence('oknte-real-plan')
    try {
      const snapshot = await (
        await page.request.get(`${backend}/api/dispatch/runtime-snapshot`)
      ).json()
      expect(snapshot.tasks).toHaveLength(0)
      const started = await post('/api/dispatch/start', {
        mode: 'AutoProxy',
        tasks: {
          '0': {
            uid: '-',
            children: { '0': { uid: scriptId, children: { '0': { uid: userId } } } },
          },
        },
      })
      taskId = started.taskId
      await expect
        .poll(
          async () => {
            const current = JSON.parse(await readFile(path.join(configDir, dailyFiles[1]), 'utf8'))
            if (current.daily_anomaly?.['目标消耗体力'] !== 200) return false
            expect(current.daily_anomaly['具体奖励目标']).toBe('角色经验')
            expect(current.daily_anomaly['循环模式']).toBe(base.daily_anomaly['循环模式'])
            expect(current.daily_claim).toEqual(base.daily_claim)
            const routine = JSON.parse(await readFile(path.join(configDir, dailyFiles[0]), 'utf8'))
            expect(
              routine['Routine Items'].find((item: { id: string }) => item.id === 'coffee').enabled
            ).toBe(false)
            expect(
              routine['Routine Items'].find((item: { id: string }) => item.id === 'daily_claim')
                .enabled
            ).toBe(true)
            injected = true
            return true
          },
          { timeout: 120_000, intervals: [250, 500, 1000] }
        )
        .toBe(true)
      await app.goto('/scheduler')
      await app.evidence('oknte-real-running')
      await expect
        .poll(
          async () => {
            const status = await (
              await page.request.get(`${backend}/api/dispatch/task/${taskId}`, { maxRetries: 2 })
            ).json()
            finalStatus = status.status
            return finalStatus
          },
          { timeout: 35 * 60 * 1000, intervals: [2000, 5000] }
        )
        .toMatch(/^(success|error|cancelled)$/)
      await expect.poll(() => completion, { timeout: 15_000 }).toBeDefined()
      expect(finalStatus).toBe('success')
      const projected = projectTaskTree(completion!.task)
      const account = projected
        .find(item => item.config_id === scriptId)
        ?.userList.find(item => item.config_id === userId)
      expect(account?.status).toBe('完成')
      await app.evidence('oknte-real-complete')
    } finally {
      if (taskId) {
        const status = await (
          await page.request.get(`${backend}/api/dispatch/task/${taskId}`)
        ).json()
        if (status.status === 'running') await post('/api/dispatch/stop', { taskId })
        await expect
          .poll(
            async () => {
              const state = await (
                await page.request.get(`${backend}/api/dispatch/runtime-snapshot`)
              ).json()
              return state.tasks.length
            },
            { timeout: 90_000 }
          )
          .toBe(0)
      }
      const nativeAfter = await Promise.all(
        dailyFiles.map(file => readFile(path.join(configDir, file), 'utf8'))
      )
      const quickAfter = await Promise.all(
        dailyFiles.map(file => readFile(path.join(quickDir, file), 'utf8'))
      )
      restored = JSON.stringify(nativeAfter) === JSON.stringify(nativeBefore)
      await writeFile(
        testInfo.outputPath('real-e2e-summary.json'),
        JSON.stringify(
          {
            injected,
            restored,
            quickUnchanged: JSON.stringify(quickAfter) === JSON.stringify(quickBefore),
            finalStatus,
            completion: completion
              ? {
                  outcome: completion.outcome,
                  accounts: projectTaskTree(completion.task).flatMap(script =>
                    script.userList.map(user => ({ status: user.status }))
                  ),
                }
              : null,
          },
          null,
          2
        )
      )
      expect(nativeAfter).toEqual(nativeBefore)
      expect(quickAfter).toEqual(quickBefore)
    }
  })
})
