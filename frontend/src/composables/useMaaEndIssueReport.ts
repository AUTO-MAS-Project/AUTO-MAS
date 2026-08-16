import { message } from 'ant-design-vue'
import { ref } from 'vue'

import { showMaaEndIssueReportGuide } from '@/utils/maaEndIssueReport'

interface ReportLogger {
  info: (message: string) => void | Promise<void>
  error: (message: string) => void | Promise<void>
}

export function useMaaEndIssueReport(logger: ReportLogger) {
  const exporting = ref(false)

  const exportMaaEndIssueReport = async () => {
    exporting.value = true
    try {
      const result = await window.electronAPI?.exportMaaEndIssueReport?.()

      if (!result) {
        message.error('导出功能未响应，请检查程序')
        logger.error('导出 MaaEnd 问题包失败: 未收到响应')
        return
      }

      if (result.success) {
        message.success(result.message || 'MaaEnd 问题包导出成功')
        logger.info(`MaaEnd 问题包导出成功: ${result.zipPath || '路径未知'}`)
        if (result.zipPath) {
          await window.electronAPI?.showItemInFolder?.(result.zipPath)
        }
        showMaaEndIssueReportGuide(result.zipPath)
        return
      }

      const errorMsg = result.error || 'MaaEnd 问题包导出失败'
      logger.error(`导出 MaaEnd 问题包失败: ${errorMsg}`)
      message.error(errorMsg)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`导出 MaaEnd 问题包失败: ${errorMsg}`)
      message.error(`导出问题包异常: ${errorMsg}`)
    } finally {
      exporting.value = false
    }
  }

  return { exporting, exportMaaEndIssueReport }
}
