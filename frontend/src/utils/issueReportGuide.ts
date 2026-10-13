import { translate as t } from '@/i18n'
import { Modal } from 'ant-design-vue'

import { MAS_QQ_GROUP_URL, openExternalUrl } from './openExternal'

const getZipFileName = (zipPath: string | undefined, fallbackName: string): string => {
  if (!zipPath) return fallbackName
  return zipPath.split(/[\\/]/).pop() || fallbackName
}

export function showIssueReportGuide(zipPath: string | undefined, fallbackName: string): void {
  const fileName = getZipFileName(zipPath, fallbackName)

  Modal.info({
    title: t('misc.sendIssueBundleMas'),
    closable: true,
    content: t('misc.issueReportGuide', { fileName }),
    okText: t('misc.openMasGroup'),
    onOk: () => openExternalUrl(MAS_QQ_GROUP_URL),
  })
}
