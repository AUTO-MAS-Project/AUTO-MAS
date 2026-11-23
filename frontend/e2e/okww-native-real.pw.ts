import { readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { expect, test } from './fixtures'
import { observeMainConnection } from './socket-recovery'
import { projectTaskTree } from '../src/composables/taskTreeProjection'
import type { TaskItemDocument } from '../src/api'

const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
const files = {
  daily: 'DailyTask.json',
  echo: 'FarmEchoTask.json',
  nightmare: 'NightmareNestTask.json',
  combat: 'AutoCombatTask.json',
  character: 'Character Config.json',
  monthly: 'Monthly Card Config.json',
} as const

test.describe('@real @okww-native-real', () => {
  test.skip(process.env.AUTO_MAS_E2E_REAL !== '1', '需要本机真实运行环境')
  test('saves native panels, runs daily with one 4C boss, and restores native files', async ({
    app,
    page,
  }, testInfo) => {
    test.setTimeout(45 * 60 * 1000)
    const scriptId = process.env.AUTO_MAS_E2E_SCRIPT_ID!
    const userId = process.env.AUTO_MAS_E2E_USER_ID!
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
    await expect(page.locator('.task-control')).toBeVisible({ timeout: 30_000 })
    const script = (await post('/api/scripts/get', { scriptId })).data[scriptId]
    const users = (await post('/api/scripts/user/get', { scriptId })).data
    expect(Object.keys(users)).toEqual([userId])
    expect(users[userId].Info.Name).toBe(process.env.AUTO_MAS_E2E_ACCOUNT_NAME)
    const install = process.env.AUTO_MAS_E2E_OKWW_ROOT ?? script.Info.RootPath
    const configDir = path.join(install, 'data/apps/ok-ww/working/configs')
    const snapshot = async () =>
      Promise.all(
        Object.values(files).map(async file => {
          try {
            return await readFile(path.join(configDir, file), 'utf8')
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null
            throw error
          }
        })
      )
    const before = await snapshot()
    await post('/api/scripts/update', {
      scriptId,
      data: {
        Info: { RootPath: install },
        Run: { RunTimesLimit: 1 },
        Game: { IfAutoUpdate: false, Type: 'Client' },
      },
    })
    await post('/api/scripts/user/update', {
      scriptId,
      userId,
      data: {
        Info: { IfQuickConfig: true, PlanMode: 'Fixed' },
        Task: { IfCustomArguments: false },
      },
    })
    const patches = {
      daily: {
        'Which to Farm': 'Tacet Suppression',
        'Which Tacet Suppression to Farm': 1,
        'Farm Nightmare Nest for Daily Echo': true,
        'Additional Tasks to Run After Daily Task': ['Teleport and Farm 4C Echo'],
      },
      echo: {
        'Teleport to Boss': 'Boss Challenge',
        'Which Boss Challenge to Teleport': 1,
        'Repeat Farm Count': 1,
        'Use Liberation': true,
      },
      nightmare: { 'Which to Farm': ['Nightmare Purification'] },
      combat: { 'Switch to Healer before and after Combat': true },
      character: { 'Roccia C6': false },
      monthly: { 'Check Monthly Card': false, 'Monthly Card Time': 4 },
    }
    for (const [kind, values] of Object.entries(patches))
      await post('/api/scripts/okww/task-config', { scriptId, userId, kind, values })
    // 从真实配置页保存刷取次数，验证控件到原生文件的完整路径。
    await app.goto(`/scripts/${scriptId}/users/${userId}/edit/okww`)
    await page.getByRole('tab', { name: '4C Echo settings', exact: true }).click()
    const count = page
      .locator('.ant-form-item')
      .filter({ has: page.locator('label').filter({ hasText: 'Repeat Farm Count' }) })
      .getByRole('spinbutton')
    await expect(count).toHaveValue('1')
    const saved = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await count.fill('2')
    expect((await (await saved).json()).code).toBe(200)
    await expect(count).toBeEnabled()
    const savedAgain = page.waitForResponse(
      r => r.url().endsWith('/api/scripts/okww/task-config') && r.request().method() === 'POST'
    )
    await count.fill('1')
    expect((await (await savedAgain).json()).code).toBe(200)
    await expect(count).toBeEnabled()
    await app.evidence('okww-native-real-config')
    try {
      const state = await (
        await page.request.get(`${backend}/api/dispatch/runtime-snapshot`)
      ).json()
      expect(state.tasks).toHaveLength(0)
      taskId = (
        await post('/api/dispatch/start', {
          mode: 'AutoProxy',
          tasks: {
            '0': {
              uid: '-',
              children: { '0': { uid: scriptId, children: { '0': { uid: userId } } } },
            },
          },
        })
      ).taskId
      await expect
        .poll(
          async () => {
            const status = await (
              await page.request.get(`${backend}/api/dispatch/task/${taskId}`)
            ).json()
            finalStatus = status.status
            if (['error', 'cancelled'].includes(finalStatus)) {
              throw new Error(`配置下发前任务已结束: ${finalStatus}`)
            }
            for (const [kind, patch] of Object.entries(patches)) {
              const native = JSON.parse(
                await readFile(path.join(configDir, files[kind as keyof typeof files]), 'utf8')
              )
              for (const [key, value] of Object.entries(patch))
                if (JSON.stringify(native[key]) !== JSON.stringify(value)) return false
            }
            injected = true
            return true
          },
          { timeout: 180_000, intervals: [500, 1000, 2000] }
        )
        .toBe(true)
      await app.goto('/scheduler')
      await app.evidence('okww-native-real-running')
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
      const account = projectTaskTree(completion!.task)
        .find(item => item.config_id === scriptId)
        ?.userList.find(item => item.config_id === userId)
      expect(account?.status).toBe('完成')
      await app.evidence('okww-native-real-complete')
    } finally {
      if (taskId) {
        const status = await (
          await page.request.get(`${backend}/api/dispatch/task/${taskId}`)
        ).json()
        if (status.status === 'running') await post('/api/dispatch/stop', { taskId })
        await expect
          .poll(
            async () =>
              (await (await page.request.get(`${backend}/api/dispatch/runtime-snapshot`)).json())
                .tasks.length,
            { timeout: 90_000 }
          )
          .toBe(0)
      }
      const after = await snapshot()
      restored = JSON.stringify(after) === JSON.stringify(before)
      await writeFile(
        testInfo.outputPath('real-e2e-summary.json'),
        JSON.stringify(
          {
            injected,
            restored,
            finalStatus,
            outcome: completion?.outcome,
            accountStatuses: completion
              ? projectTaskTree(completion.task).flatMap(script =>
                  script.userList.map(user => user.status)
                )
              : [],
          },
          null,
          2
        )
      )
      expect(after).toEqual(before)
    }
  })
})
