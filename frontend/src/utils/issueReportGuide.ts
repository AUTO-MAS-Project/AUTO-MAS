import { translate as t } from '@/i18n'
import { openAlert } from '@/composables/useConfirm'

import { MAS_QQ_GROUP_URL, openHelpLink } from './openExternal'

const getZipFileName = (zipPath: string | undefined, fallbackName: string): string => {
  if (!zipPath) return fallbackName
  return zipPath.split(/[\\/]/).pop() || fallbackName
}

export function showIssueReportGuide(zipPath: string | undefined, fallbackName: string): void {
  const fileName = getZipFileName(zipPath, fallbackName)

  void openAlert({
    tone: 'info',
    title: t('bootstrap.misc.sendIssueBundleMas'),
    closable: true,
    description: t('bootstrap.misc.issueReportGuide', { fileName }),
    okText: t('bootstrap.misc.openMasGroup'),
    onOk: () => openHelpLink(MAS_QQ_GROUP_URL, 'support', 'other'),
  })
}
