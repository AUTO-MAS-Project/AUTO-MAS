import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

/** 初始化失败时后端可能还没启动，直接通过 Electron 导出日志。 */
export function useLogExport() {
  const { t } = useI18n()
  const exportingLogs = ref(false)

  async function packageLogs() {
    if (exportingLogs.value) return

    const logger = window.electronAPI.getLogger('日志导出')
    exportingLogs.value = true
    try {
      const result = await window.electronAPI.exportLogs?.()
      if (!result) {
        message.error(t('logs.toast.packageNoResponse'))
        logger.error('打包日志失败: 未收到响应')
        return
      }
      if (!result.success) {
        // 保存对话框取消统一返回该中文文案，静默即可。
        if (result.error === '用户取消') return
        throw new Error(result.error || t('logs.toast.packageFailed'))
      }

      message.success(result.message || t('logs.toast.packageExported'))
      logger.info(`日志打包成功: ${result.zipPath}`)
      if (result.zipPath) {
        try {
          await window.electronAPI.showItemInFolder?.(result.zipPath)
        } catch (error) {
          logger.error(`打开压缩包所在文件夹失败: ${String(error)}`)
          message.error(t('logs.toast.openFolderFailed'))
        }
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      logger.error(`打包日志失败: ${reason}`)
      message.error(t('logs.toast.packageError', { error: reason }))
    } finally {
      exportingLogs.value = false
    }
  }

  return { exportingLogs, packageLogs }
}
