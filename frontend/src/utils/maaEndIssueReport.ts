import { translate as t } from '@/i18n'
import { Modal } from 'ant-design-vue'

import { MAS_QQ_GROUP_URL, openExternalUrl } from './openExternal'

const getZipFileName = (zipPath?: string): string => {
  if (!zipPath) return 'MaaEnd-logs-*.zip'
  return zipPath.split(/[\\/]/).pop() || 'MaaEnd-logs-*.zip'
}

export function showMaaEndIssueReportGuide(zipPath?: string): void {
  const fileName = getZipFileName(zipPath)

  Modal.info({
    title: t('misc.sendIssueBundleMas'),
    content: `问题包「${fileName}」已生成。请将 ZIP 原文件直接发送到 AUTO-MAS 官方 QQ 群（群号：957750551），不要解压、修改或只复制其中的日志内容。`,
    okText: t('misc.openMasGroup'),
    onOk: () => openExternalUrl(MAS_QQ_GROUP_URL),
  })
}
