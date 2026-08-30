import { Modal } from 'ant-design-vue'

import { MAS_QQ_GROUP_URL, openExternalUrl } from './openExternal'

const getZipFileName = (zipPath: string | undefined, fallbackName: string): string => {
  if (!zipPath) return fallbackName
  return zipPath.split(/[\\/]/).pop() || fallbackName
}

export function showIssueReportGuide(
  zipPath: string | undefined,
  fallbackName: string
): void {
  const fileName = getZipFileName(zipPath, fallbackName)

  Modal.info({
    title: '请将问题包发送到 MAS 群',
    content: `问题包「${fileName}」已生成。请将 ZIP 原文件直接发送到 AUTO-MAS 官方 QQ 群（群号：957750551），不要解压、修改或只复制其中的日志内容。`,
    okText: '打开 MAS 群',
    onOk: () => openExternalUrl(MAS_QQ_GROUP_URL),
  })
}
