import { message } from 'ant-design-vue'
import { ref } from 'vue'

import { showIssueReportGuide } from '@/utils/issueReportGuide'

export interface ReportLogger {
  info: (message: string) => void | Promise<void>
  error: (message: string) => void | Promise<void>
}

interface IssueReportResult {
  success: boolean
  message?: string
  zipPath?: string
  error?: string
}

interface IssueReportOptions<Args extends unknown[]> {
  /** 产品展示名，如 'OK-WW' / 'MaaEnd' */
  label: string
  /** 问题包文件名兜底前缀，如 'OK-WW-logs-*.zip' */
  fallbackName: string
  /** 触发导出的 IPC 方法；按脚本导出的（MFW）带脚本 ID */
  exportFn: (...args: Args) => Promise<IssueReportResult | undefined> | undefined
}

export function useIssueReport<Args extends unknown[] = []>(
  logger: ReportLogger,
  options: IssueReportOptions<Args>
) {
  const exporting = ref(false)

  const exportIssueReport = async (...args: Args) => {
    exporting.value = true
    try {
      const result = await options.exportFn(...args)

      if (!result) {
        message.error('导出功能未响应，请检查程序')
        logger.error(`导出 ${options.label} 问题包失败: 未收到响应`)
        return
      }

      if (result.success) {
        message.success(result.message || `${options.label} 问题包导出成功`)
        logger.info(`导出 ${options.label} 问题包成功: ${result.zipPath || '路径未知'}`)
        if (result.zipPath) {
          await window.electronAPI?.showItemInFolder?.(result.zipPath)
        }
        showIssueReportGuide(result.zipPath, options.fallbackName)
        return
      }

      // 在保存对话框里点了取消（主进程 registerIssueReportExporter 的约定），不算失败
      if (result.error === '用户取消') {
        return
      }

      const errorMsg = result.error || `${options.label} 问题包导出失败`
      logger.error(`导出 ${options.label} 问题包失败: ${errorMsg}`)
      message.error(errorMsg)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`导出 ${options.label} 问题包失败: ${errorMsg}`)
      message.error(`导出问题包异常: ${errorMsg}`)
    } finally {
      exporting.value = false
    }
  }

  return { exporting, exportIssueReport }
}
