type Cleanup = {
  startAttempted: boolean
  taskId: string | undefined
  findTask: () => Promise<string | undefined>
  terminateTask: (taskId: string) => Promise<void>
  waitForIdle: () => Promise<void>
  closeEmulator: () => Promise<void>
}

export async function cleanupRealRun(cleanup: Cleanup): Promise<void> {
  if (cleanup.startAttempted) {
    const taskId = cleanup.taskId ?? (await cleanup.findTask())
    if (!taskId) throw new Error('启动已发起，但无法确认任务；保留模拟器供人工检查')
    await cleanup.terminateTask(taskId)
  }
  await cleanup.waitForIdle()
  await cleanup.closeEmulator()
}
