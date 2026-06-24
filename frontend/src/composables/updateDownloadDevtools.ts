import { useUpdateDownload, type UpdateDownloadStatus } from './useUpdateDownload'
import { useUpdateModal } from './useUpdateChecker'

const assertDevelopment = () => {
  if (!import.meta.env.DEV) {
    throw new Error('更新下载调试工具仅可在开发模式使用')
  }
}

export function useUpdateDownloadDevtools() {
  assertDevelopment()

  const download = useUpdateDownload()
  const updateModal = useUpdateModal()

  const simulateUpdateAvailable = (version: string) => {
    assertDevelopment()
    updateModal.showUpdateModal(
      {
        新功能: ['更新下载测试页模拟的版本更新'],
        修复: ['取消、后台下载、失败恢复与切源状态'],
      },
      version
    )
  }

  const simulateProgress = (
    source: 'GitHub' | 'CNB' | 'MirrorChyan' | 'AutoSite',
    percent: number,
    speedBytesPerSecond: number
  ) => {
    assertDevelopment()
    const fileSize = 100 * 1024 * 1024
    download.status.value = 'downloading'
    download.modalVisible.value = true
    download.receiveProgress({
      downloaded_size: Math.round((fileSize * percent) / 100),
      file_size: fileSize,
      speed: speedBytesPerSecond,
      source,
    })
  }

  const simulateStatus = (nextStatus: UpdateDownloadStatus, reason = '') => {
    assertDevelopment()
    download.status.value = nextStatus
    download.failureReason.value = reason
    download.modalVisible.value = nextStatus !== 'idle'
  }

  const simulateFailure = (reason: string) => {
    assertDevelopment()
    download.receiveSignal({ Failed: reason })
  }

  const simulateCompletion = () => {
    assertDevelopment()
    download.receiveSignal({ Accomplish: 'dev-update-package.zip' })
  }

  const resetSimulation = () => {
    assertDevelopment()
    download.reset()
  }

  return {
    simulateUpdateAvailable,
    simulateProgress,
    simulateStatus,
    simulateFailure,
    simulateCompletion,
    resetSimulation,
  }
}
