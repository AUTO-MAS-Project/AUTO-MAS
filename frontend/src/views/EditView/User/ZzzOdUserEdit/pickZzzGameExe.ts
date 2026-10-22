import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
/** 弹出文件选择并校验为 ZenlessZoneZero.exe，取消/选错返回 null（两处共用） */
export const pickZzzGameExe = async (): Promise<string | null> => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'ZenlessZoneZero.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return null
  const fileName = path.split(/[\\/]/).pop()
  if (fileName?.toLowerCase() !== 'zenlesszonezero.exe') {
    message.error(t('edit.zzzodPickGameExe'))
    return null
  }
  return path
}
