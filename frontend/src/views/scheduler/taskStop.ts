import type { OutBase } from '@/api/models/OutBase'

export const isTaskStopConfirmed = (response: OutBase): boolean =>
  response.code === 200 || response.message?.includes('未找到对应任务') === true
