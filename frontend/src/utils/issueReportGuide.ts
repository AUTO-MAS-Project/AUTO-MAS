import { translate as t } from '@/i18n'
import { Modal } from 'ant-design-vue'

import { MAS_QQ_GROUP_URL, openHelpLink } from './openExternal'

const getZipFileName = (zipPath: string | undefined, fallbackName: string): string => {
  if (!zipPath) return fallbackName
  return zipPath.split(/[\\/]/).pop() || fallbackName
}

export function showIssueReportGuide(zipPath: string | undefined, fallbackName: string): void {
  const fileName = getZipFileName(zipPath, fallbackName)

  Modal.info({
    title: t('bootstrap.misc.sendIssueBundleMas'),
    closable: true,
    content: t('bootstrap.misc.issueReportGuide', { fileName }),
    okText: t('bootstrap.misc.openMasGroup'),
    onOk: () => openHelpLink(MAS_QQ_GROUP_URL, 'support', 'other'),
  })
}
