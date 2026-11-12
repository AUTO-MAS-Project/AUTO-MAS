import { Modal } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { getTaskRuntimeStates } from './useTaskRuntimeState'

// 关闭判断读取常驻运行状态，不从持久化的界面草稿推断运行结果。
export const hasRunningTasks = (): boolean =>
  getTaskRuntimeStates().some(task => task.phase !== 'completed')

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
