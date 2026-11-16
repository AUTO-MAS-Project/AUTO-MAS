import { message, Modal } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import type { StorageEntry } from './types'

export const copyDevtoolsText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    message.success(t('core.devtools.copied'))
  } catch {
    message.error(t('core.devtools.copyFailed'))
  }
}

export const confirmDevtoolsAction = (title: string, content: string): Promise<boolean> =>
  new Promise(resolve => {
    Modal.confirm({
      title,
      content,
      okText: t('core.devtools.confirm'),
      cancelText: t('core.devtools.cancel'),
      okType: 'danger',
      onOk: () => {
        resolve(true)
      },
      onCancel: () => {
        resolve(false)
      },
    })
  })

export const formatBytes = (bytes: number): string =>
  bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KiB`

export const readStorageEntries = (storage: Storage): StorageEntry[] => {
  const entries: StorageEntry[] = []
  for (let index = 0; index < storage.length; index++) {
    const key = storage.key(index)
    if (key === null) continue
    const value = storage.getItem(key)
    if (value === null) continue
    let type: StorageEntry['type'] = 'text'
    try {
      JSON.parse(value)
      type = 'json'
    } catch {
      // 原始字符串也是合法存储内容，不能以 JSON 校验拒绝它。
    }
    entries.push({ key, value, type, bytes: (key.length + value.length) * 2 })
  }
  return entries.sort((left, right) => left.key.localeCompare(right.key))
}
