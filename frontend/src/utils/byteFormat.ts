/**
 * 字节量与吞吐的人类可读格式化。
 *
 * 二进制换算（1 KB = 1024 B），单位到 GB 为止；更新下载弹窗与初始化页的下载细节
 * 共用同一套口径，两处显示的数字才对得上。
 */

const BASE = 1024
const SIZE_UNITS = ['B', 'KB', 'MB', 'GB'] as const
const SPEED_UNITS = ['B/s', 'KB/s', 'MB/s', 'GB/s'] as const

function unitIndex(value: number, units: readonly string[]): number {
  return Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(BASE)))
}

/** `1536` → `1.5 KB`；小数最多两位，去掉尾零。 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const index = unitIndex(bytes, SIZE_UNITS)
  return `${parseFloat((bytes / Math.pow(BASE, index)).toFixed(2))} ${SIZE_UNITS[index]}`
}

/** `3355443` → `3.2 MB/s`；小数最多一位，去掉尾零。 */
export function formatSpeed(bytesPerSecond: number): string {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return '0 B/s'
  const index = unitIndex(bytesPerSecond, SPEED_UNITS)
  const value = bytesPerSecond / Math.pow(BASE, index)
  return `${parseFloat(value.toFixed(1))} ${SPEED_UNITS[index]}`
}
