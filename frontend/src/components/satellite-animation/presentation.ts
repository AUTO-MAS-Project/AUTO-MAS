import type { SatelliteVisualStatus } from '@/composables/useSatelliteStatus'

export interface SatelliteStatusMeta {
  label: string
  color?: string
}

export const SATELLITE_STATUS_META: Record<SatelliteVisualStatus, SatelliteStatusMeta> = {
  unknown: { label: '未知' },
  idle: { label: '空闲' },
  queued: { label: '已入队', color: 'green' },
  running: { label: '运行中', color: 'green' },
  warning: { label: '运行异常', color: 'gold' },
  failed: { label: '运行失败', color: 'red' },
}

export const SATELLITE_LEGEND_ITEMS: Array<{
  state: SatelliteVisualStatus
  label: string
}> = [
  { state: 'queued', label: '已入队' },
  { state: 'running', label: '运行中' },
  { state: 'warning', label: '运行异常' },
  { state: 'failed', label: '运行失败' },
  { state: 'idle', label: '空闲' },
]
