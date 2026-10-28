import { Modal } from 'ant-design-vue'
import { translate as t } from '@/i18n'

const logger = window.electronAPI.getLogger('窗口关闭确认')

export const hasRunningTasks = (): boolean => {
  try {
    const saved = sessionStorage.getItem('scheduler-tabs-session')
    if (saved) {
      const tabs: unknown = JSON.parse(saved)
      if (Array.isArray(tabs)) {
        return tabs.some(
          (tab: unknown) =>
            typeof tab === 'object' && tab !== null && 'status' in tab && tab.status === '运行'
        )
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`检查运行任务状态失败: ${errorMsg}`)
  }
  return false
}

export const confirmCloseIfRunningTasks = (): Promise<boolean> => {
  if (!hasRunningTasks()) return Promise.resolve(true)

  return new Promise(resolve => {
    Modal.confirm({
      title: t('bootstrap.comp.confirmExit'),
      content: t('bootstrap.comp.queueStillRunningClose'),
      okText: t('bootstrap.comp.confirmExit'),
      cancelText: t('bootstrap.comp.cancel'),
      okType: 'danger',
      centered: true,
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    })
  })
}
