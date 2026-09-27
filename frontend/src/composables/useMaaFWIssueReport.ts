import { useIssueReport } from './useIssueReport'
import type { ReportLogger } from './useIssueReport'

export function useMaaFWIssueReport(logger: ReportLogger) {
  const { exporting, exportIssueReport } = useIssueReport(logger, {
    label: 'MFW',
    fallbackName: 'MFW-logs-*.zip',
    exportFn: (scriptId: string) => window.electronAPI?.exportMaaFWIssueReport?.(scriptId),
  })
  return { exporting, exportMaaFWIssueReport: exportIssueReport }
}
