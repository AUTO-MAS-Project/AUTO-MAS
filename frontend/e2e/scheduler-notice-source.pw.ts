import { expect, test } from './fixtures'

test('@scheduler mixed-queue errors open MaaEnd export only for MaaEnd notices', async ({
  app,
  page,
}) => {
  await app.goto('/scheduler')
  const taskId = '09dd65a9-b3bf-4eba-ace5-045491299989'
  const dispatch = (id: string, type: string, data: unknown) =>
    page.evaluate(
      async ({ id, type, data }) => {
        const module = '/src/services/websocket/subscriptions.ts'
        const { dispatchMessage } = await import(module)
        dispatchMessage({ id, type, data })
      },
      { id, type, data }
    )

  await dispatch('TaskManager', 'task.created', {
    taskId,
    taskName: 'Mixed queue',
    mode: 'AutoProxy',
    trigger: 'manual',
    scripts: [
      { scriptId: 'maaend', scriptType: 'MaaEnd' },
      { scriptId: 'okww', scriptType: 'Okww' },
    ],
  })
  const maaEndTitle = page.getByText('MaaEnd task failed', { exact: true })
  await dispatch(taskId, 'task.notice', { level: 'error', message: 'OK-WW connection failed' })
  await expect(page.getByText('Task error', { exact: true })).toBeVisible()
  await expect(page.getByText('OK-WW connection failed', { exact: true })).toBeVisible()
  await expect(maaEndTitle).toHaveCount(0)

  const maaEndMessage = 'Failed to initialize controller'
  await dispatch(taskId, 'task.notice', {
    level: 'error',
    sourceScriptType: 'MaaEnd',
    message: maaEndMessage,
  })
  await expect(maaEndTitle).toBeVisible()
  await expect(page.getByText(maaEndMessage, { exact: true })).toBeVisible()
})
