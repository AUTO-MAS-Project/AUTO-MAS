import { describe, expect, it } from 'vitest'
import {
  SCHEDULER_CONNECTION_STATE_LABEL,
  SCHEDULER_CONNECTION_STATE_COLOR,
  SCHEDULER_TAB_STATUS_VALUES,
  isValidSchedulerTabStatus,
  TAB_STATUS_COLOR,
  getQueueStatusColor,
  getTaskModeOptions,
  TASK_MODE_OPTIONS,
  type SchedulerConnectionState,
  type SchedulerTabStatus,
} from './schedulerConstants'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

describe('schedulerConstants', () => {
  describe('SCHEDULER_CONNECTION_STATE_LABEL', () => {
    it('所有连接状态都有对应的中文标签', () => {
      const states: SchedulerConnectionState[] = [
        'idle',
        'connecting',
        'connected',
        'disconnected',
        'reconnecting',
        'failed',
        'offline',
      ]
      for (const state of states) {
        expect(SCHEDULER_CONNECTION_STATE_LABEL[state]).toBeTruthy()
        expect(typeof SCHEDULER_CONNECTION_STATE_LABEL[state]).toBe('string')
      }
    })

    it('各状态标签正确', () => {
      expect(SCHEDULER_CONNECTION_STATE_LABEL.idle).toBe('未连接')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.connecting).toBe('连接中')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.connected).toBe('已连接')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.disconnected).toBe('已断开')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.reconnecting).toBe('重连中')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.failed).toBe('连接失败')
      expect(SCHEDULER_CONNECTION_STATE_LABEL.offline).toBe('离线')
    })
  })

  describe('SCHEDULER_CONNECTION_STATE_COLOR', () => {
    it('所有连接状态都有对应的颜色', () => {
      const states: SchedulerConnectionState[] = [
        'idle',
        'connecting',
        'connected',
        'disconnected',
        'reconnecting',
        'failed',
        'offline',
      ]
      for (const state of states) {
        expect(SCHEDULER_CONNECTION_STATE_COLOR[state]).toBeTruthy()
      }
    })

    it('已连接状态为 success 颜色', () => {
      expect(SCHEDULER_CONNECTION_STATE_COLOR.connected).toBe('success')
    })

    it('失败状态为 error 颜色', () => {
      expect(SCHEDULER_CONNECTION_STATE_COLOR.failed).toBe('error')
    })

    it('连接中和重连中状态为 processing 颜色', () => {
      expect(SCHEDULER_CONNECTION_STATE_COLOR.connecting).toBe('processing')
      expect(SCHEDULER_CONNECTION_STATE_COLOR.reconnecting).toBe('processing')
    })
  })

  describe('SCHEDULER_TAB_STATUS_VALUES', () => {
    it('包含完整状态机：空闲/运行/停止中/结束/失败', () => {
      expect(SCHEDULER_TAB_STATUS_VALUES).toEqual(['空闲', '运行', '停止中', '结束', '失败'])
    })

    it('不包含旧的 等待/异常 等无效状态', () => {
      expect(SCHEDULER_TAB_STATUS_VALUES).not.toContain('等待')
      expect(SCHEDULER_TAB_STATUS_VALUES).not.toContain('异常')
    })
  })

  describe('isValidSchedulerTabStatus', () => {
    it('合法状态返回 true', () => {
      expect(isValidSchedulerTabStatus('空闲')).toBe(true)
      expect(isValidSchedulerTabStatus('运行')).toBe(true)
      expect(isValidSchedulerTabStatus('停止中')).toBe(true)
      expect(isValidSchedulerTabStatus('结束')).toBe(true)
      expect(isValidSchedulerTabStatus('失败')).toBe(true)
    })

    it('非法状态返回 false', () => {
      expect(isValidSchedulerTabStatus('等待')).toBe(false)
      expect(isValidSchedulerTabStatus('异常')).toBe(false)
      expect(isValidSchedulerTabStatus('')).toBe(false)
      expect(isValidSchedulerTabStatus('running')).toBe(false)
    })

    it('作为类型守卫收窄类型', () => {
      const raw: string = '停止中'
      if (isValidSchedulerTabStatus(raw)) {
        // 此处 raw 应收窄为 SchedulerTabStatus
        const _typed: SchedulerTabStatus = raw
        expect(_typed).toBe('停止中')
      }
    })
  })

  describe('TAB_STATUS_COLOR', () => {
    it('所有调度台状态都有对应的颜色', () => {
      // 覆盖完整状态机，包含 Lane 09 新增的 停止中/失败
      const statuses: SchedulerTabStatus[] = ['空闲', '运行', '停止中', '结束', '失败']
      for (const status of statuses) {
        expect(TAB_STATUS_COLOR[status]).toBeTruthy()
      }
    })

    it('空闲状态为 default', () => {
      expect(TAB_STATUS_COLOR['空闲']).toBe('default')
    })

    it('运行状态为 processing', () => {
      expect(TAB_STATUS_COLOR['运行']).toBe('processing')
    })

    it('停止中状态为 warning（Lane 09 新增）', () => {
      expect(TAB_STATUS_COLOR['停止中']).toBe('warning')
    })

    it('结束状态为 success', () => {
      expect(TAB_STATUS_COLOR['结束']).toBe('success')
    })

    it('失败状态为 error（Lane 09 新增）', () => {
      expect(TAB_STATUS_COLOR['失败']).toBe('error')
    })
  })

  describe('getQueueStatusColor', () => {
    it('成功/完成/已完成 → green', () => {
      expect(getQueueStatusColor('成功')).toBe('green')
      expect(getQueueStatusColor('已完成')).toBe('green')
      expect(getQueueStatusColor('完成')).toBe('green')
    })

    it('失败/错误/异常 → red', () => {
      expect(getQueueStatusColor('失败')).toBe('red')
      expect(getQueueStatusColor('错误')).toBe('red')
      expect(getQueueStatusColor('异常')).toBe('red')
    })

    it('等待/排队/挂起 → orange', () => {
      expect(getQueueStatusColor('等待')).toBe('orange')
      expect(getQueueStatusColor('排队')).toBe('orange')
      expect(getQueueStatusColor('挂起')).toBe('orange')
    })

    it('进行/执行/运行 → blue', () => {
      expect(getQueueStatusColor('运行中')).toBe('blue')
      expect(getQueueStatusColor('执行中')).toBe('blue')
      expect(getQueueStatusColor('进行中')).toBe('blue')
    })

    it('未知状态 → default', () => {
      expect(getQueueStatusColor('unknown')).toBe('default')
      expect(getQueueStatusColor('')).toBe('default')
    })
  })

  describe('TASK_MODE_OPTIONS', () => {
    it('包含自动代理、人工排查和循环运行', () => {
      expect(TASK_MODE_OPTIONS).toHaveLength(3)
      expect(TASK_MODE_OPTIONS[0].value).toBe(TaskCreateIn.mode.AUTO_PROXY)
      expect(TASK_MODE_OPTIONS[1].value).toBe(TaskCreateIn.mode.MANUAL_REVIEW)
      expect(TASK_MODE_OPTIONS[2].value).toBe(TaskCreateIn.mode.CYCLE_RUN)
    })
  })

  describe('getTaskModeOptions', () => {
    it('无 supportedModes 时返回全部选项', () => {
      expect(getTaskModeOptions()).toEqual(TASK_MODE_OPTIONS)
      expect(getTaskModeOptions(null)).toEqual(TASK_MODE_OPTIONS)
    })

    it('空数组时返回空', () => {
      const options = getTaskModeOptions([])
      expect(options).toHaveLength(0)
    })

    it('按 supportedModes 过滤', () => {
      const options = getTaskModeOptions([
        TaskCreateIn.mode.AUTO_PROXY,
        TaskCreateIn.mode.CYCLE_RUN,
      ])
      expect(options).toHaveLength(2)
      expect(options[0].value).toBe(TaskCreateIn.mode.AUTO_PROXY)
      expect(options[1].value).toBe(TaskCreateIn.mode.CYCLE_RUN)
    })
  })
})
