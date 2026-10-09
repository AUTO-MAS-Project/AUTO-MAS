import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useMaaIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MAA',
    fallbackName: 'MAA-logs-*.zip',
    exportFn: () => window.electronAPI?.exportMaaIssueReport?.(),
  })
  return { exporting, exportMaaIssueReport: exportIssueReport }
}
