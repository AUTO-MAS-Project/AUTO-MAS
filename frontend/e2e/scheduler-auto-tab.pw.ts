import { expect, test } from './fixtures'

test('@scheduler an automatic run restores its selected queue after reconnect', async ({
  app,
  page,
}) => {
  const backend = `http://127.0.0.1:${process.env.AUTO_MAS_E2E_BACKEND_PORT ?? 36174}`
  const created = await page.request.post(`${backend}/api/queue/add`, { data: {} })
  const { queueId } = await created.json()
  expect(queueId).toBeTruthy()
  const name = 'Scheduled queue for rerun'
  const renamed = await page.request.post(`${backend}/api/queue/update`, {
    data: { queueId, data: { Info: { Name: name } } },
  })
  expect((await renamed.json()).code).toBe(200)

  const taskId = '09dd65a9-b3bf-4eba-ace5-045491299989'
  const runInfo = { name, mode: 'AutoProxy', status: 'running', trigger: 'timed' }
  let running = true
  await page.route('**/api/dispatch/runtime-snapshot', route =>
    route.fulfill({
      json: {
        tasks: running
          ? [
              {
                taskId,
                targetId: queueId,
                mode: 'AutoProxy',
                trigger: 'timed',
                task: { info: runInfo },
              },
            ]
          : [],
      },
    })
  )
  try {
    await app.goto('/scheduler')
    const control = page.locator('.task-control:visible')
    await expect(control.getByRole('button', { name: /Stop/ })).toBeVisible()
    running = false
    await page.evaluate(
      async ({ taskId, runInfo }) => {
        const module = '/src/services/websocket/subscriptions.ts'
        const { dispatchMessage } = await import(module)
        dispatchMessage({
          id: taskId,
          type: 'task.completed',
          data: {
            outcome: 'success',
            result: 'Success!',
            task: { info: { ...runInfo, status: 'success' } },
          },
        })
      },
      { taskId, runInfo }
    )
    await expect(control.locator('.ant-select-selection-item').first()).toContainText(name)
  } finally {
    await page.request.post(`${backend}/api/queue/delete`, { data: { queueId } })
  }
})
