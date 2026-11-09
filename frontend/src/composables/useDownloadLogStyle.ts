import { computed, type Ref } from 'vue'
import type { WSTaskPrefetchData } from '@/services/websocket/types'
import { translate as t } from '@/i18n'
import { useLogHighlight, type LogHighlightColors } from './useLogHighlight'

export const downloadFields = [
  'target',
  'package',
  'method',
  'status',
  'progress',
  'size',
  'rate',
] as const
export type DownloadField = (typeof downloadFields)[number]
export const downloadFamilies = {
  blue: 215,
  cyan: 183,
  green: 135,
  orange: 32,
  purple: 280,
  pink: 337,
}

export const sampleDownload: WSTaskPrefetchData = {
  target: 'MaaEnd',
  package: 'MaaEnd-update.zip',
  method: 'FluxDown',
  status: '下载中',
  progress: '42.0%',
  size: '84.0/200.0 MiB',
  rate: '5.2 MiB/s',
}

export const downloadColorKey = (field: DownloadField) =>
  `download${field[0].toUpperCase()}${field.slice(1)}` as keyof LogHighlightColors

/** 只组合展示字段，绝不改写脚本日志的增量基线。 */
export function getDownloadParts(data?: WSTaskPrefetchData | null) {
  if (!data) return []
  const parts: Array<{ field: DownloadField; text: string }> = []
  if (data.target)
    parts.push({ field: 'target', text: t('core.comp.prefetchTarget', { name: data.target }) })
  if (data.method) parts.push({ field: 'method', text: `[${data.method}]` })
  for (const field of ['status', 'package', 'progress', 'size', 'rate'] as const) {
    if (data[field]) parts.push({ field, text: data[field] })
  }
  return parts
}

export function useDownloadLogStyle(isDark: Readonly<Ref<boolean>>) {
  const { lightColors, darkColors, styles } = useLogHighlight()
  const downloadClasses = computed(() => ({
    'download-log-styled': true,
    'download-log-animated': styles.value.downloadGradient,
  }))
  const downloadVariables = computed(() => {
    const colors = isDark.value ? darkColors.value : lightColors.value
    const variables: Record<string, string> = {
      '--download-period': `${styles.value.downloadGradientSeconds}s`,
      '--download-background': isDark.value ? '#1e1e1e' : '#ffffff',
      '--download-foreground': isDark.value ? '#d4d4d4' : '#333333',
    }
    for (const field of downloadFields) {
      variables[`--download-${field}`] = `#${colors[downloadColorKey(field)]}`
      const family = styles.value.downloadFamilies[field] as keyof typeof downloadFamilies
      const hue = downloadFamilies[family] ?? downloadFamilies.blue
      const contrast = styles.value.downloadGradientContrast / 100
      const spread = 8 + contrast * 100
      const stops = [-spread, 0, spread].map((shift, index) => {
        const lightness = (
          isDark.value
            ? [72 - contrast * 8, 80 + contrast * 10, 76 - contrast * 5]
            : [25 - contrast * 5, 28 + contrast * 8, 27 - contrast * 4]
        )[index]
        return `hsl(${hue + shift} ${65 + contrast * 30}% ${lightness}%)`
      })
      variables[`--download-${field}-gradient`] =
        `linear-gradient(90deg, ${stops[0]}, ${stops[1]}, ${stops[2]}, ${stops[1]}, ${stops[0]})`
    }
    return variables
  })
  return { downloadClasses, downloadVariables }
}
