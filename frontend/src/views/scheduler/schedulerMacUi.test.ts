import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { existsSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const schedulerSource = readFileSync(resolve(__dirname, 'index.vue'), 'utf-8')
const schedulerLogicSource = readFileSync(resolve(__dirname, 'useSchedulerLogic.ts'), 'utf-8')
const overviewSource = readFileSync(resolve(__dirname, 'TaskOverviewPanel.vue'), 'utf-8')
const logPanelSource = readFileSync(resolve(__dirname, 'SchedulerLogPanel.vue'), 'utf-8')
const taskControlSource = readFileSync(resolve(__dirname, 'SchedulerTaskControl.vue'), 'utf-8')

describe('Scheduler mac UI contract', () => {
  it('整页只保留调度台，不再有页头、会话头块、计数条、侧栏与底部条', () => {
    // 页头与 MacSection 头块整体移除
    expect(schedulerSource).not.toContain('MacPageHeader')
    expect(schedulerSource).not.toContain('MacSection')
    expect(schedulerSource).not.toContain('调度会话，查看任务进度')
    // 旧的三个结构组件已删除且不再引用
    expect(schedulerSource).not.toContain('SchedulerSidebar')
    expect(schedulerSource).not.toContain('SchedulerStatsBar')
    expect(schedulerSource).not.toContain('SchedulerBottomBar')
    expect(existsSync(resolve(__dirname, 'SchedulerSidebar.vue'))).toBe(false)
    expect(existsSync(resolve(__dirname, 'SchedulerStatsBar.vue'))).toBe(false)
    expect(existsSync(resolve(__dirname, 'SchedulerBottomBar.vue'))).toBe(false)
    // 调度台主体存在
    expect(schedulerSource).toContain('class="scheduler-console"')
  })

  it('会话 tab 行右侧提供加会话、删当前会话与一键全删三个操作', () => {
    expect(schedulerSource).toContain('#rightExtra')
    expect(schedulerSource).toContain('console-actions')
    // 新建会话
    expect(schedulerSource).toContain('header-add-session')
    expect(schedulerSource).toContain('aria-label="新建调度会话"')
    expect(schedulerSource).toContain('@click="addSchedulerTab"')
    // 删除当前会话（仍受 currentTabCanRemove 保护）
    expect(schedulerSource).toContain('删除当前会话')
    expect(schedulerSource).toContain('currentTabCanRemove')
    // 一键全删走逻辑层批量删除（自带确认弹窗，且不删主调度台与运行中会话）
    expect(schedulerSource).toContain('一键全删')
    expect(schedulerSource).toContain('@click="removeAllNonRunningTabs"')
    expect(schedulerLogicSource).toContain("tab.key !== 'main' && tab.status !== '运行'")
  })

  it('保留真实连接状态及断线错误说明', () => {
    expect(schedulerSource).toContain('SCHEDULER_CONNECTION_STATE_LABEL[schedulerConnectionState]')
    expect(schedulerSource).toContain('v-if="!isSchedulerConnected"')
    expect(schedulerSource).toContain('connectionPanelDescription')
    expect(schedulerSource).toContain("case 'failed':")
    expect(schedulerSource).toContain('已选择的任务和现有日志不会被清空')
  })

  it('保留运行、停止、会话编辑和失败后重试链路', () => {
    expect(schedulerSource).toContain('@edit="onSchedulerTabEdit"')
    expect(schedulerSource).toContain('@start="onStartTaskClick(tab)"')
    expect(schedulerSource).toContain('@stop="stopTask(tab)"')
    expect(schedulerSource).toContain("tab.status === '停止中'")
    expect(schedulerSource).toContain("tab.status === '失败'")
    expect(schedulerSource).toContain('当前任务、模式与日志均已保留')
  })

  it('会话标签和停止过程不重复堆叠状态徽标或警告块', () => {
    expect(schedulerSource).not.toContain('class="tab-status"')
    expect(schedulerSource).not.toContain('title="正在停止任务"')
    expect(schedulerSource).not.toContain('停止请求已发送，正在等待后端结束信号')
  })

  it('不显示无法归属到单一任务的全局完成后动作', () => {
    expect(schedulerSource).not.toContain('任务完成后')
    expect(schedulerSource).not.toContain('powerAction')
    expect(schedulerSource).not.toContain('onPowerActionChange')
    expect(schedulerLogicSource).not.toContain('canChangePowerAction')
    expect(schedulerLogicSource).not.toContain('setPowerApiDispatchSetPowerPost')
    expect(schedulerLogicSource).not.toContain('getPowerApiDispatchGetPowerPost')
  })

  it('保留任务刷新、模式选择、运行停止和日志链路', () => {
    expect(schedulerSource).toContain('@refresh-tasks="loadTaskOptions"')
    expect(schedulerSource).toContain('v-model:selected-mode="tab.selectedMode"')
    expect(schedulerSource).toContain('<SchedulerLogPanel')
    expect(schedulerSource).toContain(':external-log-mode="tab.logMode"')
  })

  it('任务总览与日志面板在窄调度区降级为单列', () => {
    expect(schedulerSource).toContain('container: scheduler-workspace / inline-size')
    expect(schedulerSource).toContain('@container scheduler-workspace (max-width: 1050px)')
    expect(schedulerSource).toContain('grid-template-columns: 1fr;')
  })

  it('实时面板使用共享磨砂令牌并由主题统一处理明暗模式', () => {
    for (const panelSource of [overviewSource, logPanelSource]) {
      expect(panelSource).toContain('var(--v6-color-surface-transparent)')
      expect(panelSource).toContain('backdrop-filter: blur(18px) saturate(1.08)')
      expect(panelSource).not.toContain('var(--app-background-card-bg')
      expect(panelSource).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
      expect(panelSource).not.toContain('@media (prefers-color-scheme: dark)')
    }
  })

  it('任务控制栏按自身可用宽度换行，不依赖整个窗口宽度', () => {
    expect(taskControlSource).toContain('container: scheduler-task-control / inline-size')
    expect(taskControlSource).toContain('@container scheduler-task-control (max-width: 640px)')
    expect(taskControlSource).toContain('flex-direction: column')
    expect(taskControlSource).toContain('min-width: 0')
  })
})
