import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useMaaEndIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MaaEnd',
    fallbackName: 'MaaEnd-logs-*.zip',
    exportFn: () => window.electronAPI?.exportMaaEndIssueReport?.(),
  })
  return { exporting, exportMaaEndIssueReport: exportIssueReport }
}
