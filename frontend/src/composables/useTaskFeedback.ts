import { h, watch } from 'vue'
import { message, Modal, notification } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useAudioPlayer } from './useAudioPlayer'
import { useMaaEndIssueReport } from './useMaaEndIssueReport'
import { useBackendI18nStore } from '@/stores/backendI18n'
import { onTaskRuntimeEvent, type TaskRuntimeState } from './useTaskRuntimeState'
import type { WSTaskNoticeData } from '@/services/websocket/types'
import { resolveTaskCompletionFeedback } from '@/utils/taskFailures'

const logger = window.electronAPI.getLogger('任务反馈')
let generation = 0
let active = false
let maaEndFailureModalOpen = false
let disposeListener: (() => void) | undefined
let disposeReady: (() => void) | undefined
const pending: Array<() => void> = []

function showWhenReady(show: () => void, expectedGeneration = generation) {
  const display = () => {
    if (active && expectedGeneration === generation) show()
  }
  if (useBackendI18nStore().ready) display()
  else pending.push(display)
}

async function handleNotice(state: TaskRuntimeState, data: WSTaskNoticeData) {
  const { exportMaaEndIssueReport } = useMaaEndIssueReport(logger)
  const feedbackGeneration = generation
  const { playSound } = useAudioPlayer()
  const noticeMessage = () => (data.messageKey ? t(data.messageKey) : data.message)

  if (data.level === 'error') {
    const errorMsg = String(data.message).toLowerCase()
    const isMaaEndTask = state.scripts.some(script =>
      script.scriptType.toLowerCase().includes('maaend')
    )

    // 根据错误内容匹配具体的 noisy 模式音频
    if (
      errorMsg.includes('adb') &&
      (errorMsg.includes('连接') || errorMsg.includes('connection'))
    ) {
      await playSound('maa_adb_connection_error')
    } else if (
      errorMsg.includes('模拟器') &&
      (errorMsg.includes('未检测') ||
        errorMsg.includes('not detected') ||
        errorMsg.includes('找不到'))
    ) {
      await playSound('maa_no_emulator_detected')
    } else if (errorMsg.includes('登录') && errorMsg.includes('失败')) {
      await playSound('maa_prts_login_failed')
    } else if (errorMsg.includes('超时') || errorMsg.includes('timeout')) {
      await playSound('maa_process_timeout')
    } else if (errorMsg.includes('部分') && errorMsg.includes('失败')) {
      await playSound('maa_partial_task_failed')
    } else if (errorMsg.includes('异常') && errorMsg.includes('退出')) {
      await playSound('maa_task_exited')
    } else if (errorMsg.includes('子任务') && errorMsg.includes('失败')) {
      await playSound('subtask_failed')
    } else {
      // 默认错误音频
      await playSound('error_occurred')
    }

    const isMaaEndError = isMaaEndTask || errorMsg.includes('maaend')
    showWhenReady(() => {
      if (isMaaEndError) {
        if (!maaEndFailureModalOpen) {
          maaEndFailureModalOpen = true
          Modal.error({
            centered: true,
            closable: true,
            maskClosable: true,
            keyboard: true,
            title: t('core.scheduler.modal.maaEndFailTitle'),
            content: h('div', [
              h('p', noticeMessage()),
              h('p', t('core.scheduler.modal.maaEndFailHint')),
            ]),
            okCancel: true,
            okText: t('core.scheduler.modal.maaEndExport'),
            cancelText: t('core.scheduler.modal.maaEndSkip'),
            onOk: () => {
              void exportMaaEndIssueReport()
            },
            afterClose: () => {
              maaEndFailureModalOpen = false
            },
          })
        }
      } else {
        notification.error({
          message: t('core.scheduler.toast.taskError'),
          description: noticeMessage(),
        })
      }
    }, feedbackGeneration)
  } else if (data.level === 'warning') {
    // 播放异常音频
    await playSound('exception_occurred')
    showWhenReady(
      () =>
        notification.warning({
          message: t('core.scheduler.toast.taskWarning'),
          description: noticeMessage(),
        }),
      feedbackGeneration
    )
  } else {
    const infoMsg = String(data.message).toLowerCase()

    // 匹配成功信息的 noisy 模式音频
    if (infoMsg.includes('skland') || infoMsg.includes('森空岛')) {
      if (
        infoMsg.includes('签到成功') ||
        infoMsg.includes('checkin success') ||
        infoMsg.includes('成功')
      ) {
        await playSound('skland_checkin_success')
      } else if (
        infoMsg.includes('签到失败') ||
        infoMsg.includes('checkin failed') ||
        infoMsg.includes('失败')
      ) {
        await playSound('skland_checkin_failed')
      }
    } else if (
      infoMsg.includes('六星') ||
      infoMsg.includes('6星') ||
      infoMsg.includes('six star')
    ) {
      await playSound('six_star_report')
    } else if (infoMsg.includes('adb') && infoMsg.includes('成功')) {
      await playSound('adb_success')
    } else if (infoMsg.includes('adb') && infoMsg.includes('失败')) {
      await playSound('adb_failed')
    }

    showWhenReady(
      () =>
        notification.info({
          message: t('core.scheduler.toast.taskInfo'),
          description: noticeMessage(),
        }),
      feedbackGeneration
    )
  }
}

async function handleCompleted(state: TaskRuntimeState) {
  if (!state.outcome) return
  const feedbackGeneration = generation
  const data = {
    result: state.result ?? '',
    outcome: state.outcome,
    error: state.error,
    task_info: state.taskInfo,
  }
  const feedback = resolveTaskCompletionFeedback(data)
  const { playSound } = useAudioPlayer()
  if (feedback.kind === 'error') {
    await playSound('error_occurred')
    showWhenReady(
      () => message.error(data.error || t('core.scheduler.toast.taskRunFailed')),
      feedbackGeneration
    )
  } else if (feedback.kind === 'cancelled') {
    showWhenReady(
      () => message.warning(t('core.scheduler.toast.taskCancelled')),
      feedbackGeneration
    )
  } else if (feedback.kind === 'partialFailure') {
    await playSound('error_occurred')
    const { users, scripts } = feedback.failures
    showWhenReady(
      () =>
        message.warning(
          users > 0
            ? t('core.scheduler.toast.taskDoneWithFailedUsers', { count: users })
            : t('core.scheduler.toast.taskDoneWithFailedScripts', { count: scripts })
        ),
      feedbackGeneration
    )
  } else {
    await playSound('task_completed')
    showWhenReady(() => message.success(t('core.scheduler.toast.taskDone')), feedbackGeneration)
  }
}

/** 应用级反馈只观察生命周期与通知，不依赖任何调度台标签。 */
export function bootstrapTaskFeedback() {
  if (active) return
  active = true
  disposeReady = watch(
    () => useBackendI18nStore().ready,
    ready => {
      if (ready) pending.splice(0).forEach(show => show())
    }
  )
  disposeListener = onTaskRuntimeEvent(event => {
    if (event.type === 'notice') return handleNotice(event.state, event.notice)
    if (event.type === 'completed') return handleCompleted(event.state)
  })
}

export function disposeTaskFeedback() {
  active = false
  generation++
  pending.length = 0
  disposeReady?.()
  disposeListener?.()
  disposeReady = disposeListener = undefined
}
