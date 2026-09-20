/**
 * 配置来源（脚本级/用户级/直控）与恢复确认弹窗的前端共用判定与提示文案。
 *
 * 备份列表标签、跨来源恢复（备份来源 ≠ 当前来源）提示、源配置损坏的强制
 * 恢复确认在通用恢复组件与各专项编辑页复用，统一在此维护，避免各页各写
 * 一份比对与文案。
 */

import { h, type VNode } from 'vue'

/** 来源标签色（脚本级蓝 / 用户级绿 / 直控橙；未知值按用户级） */
export const sourceTagColor = (mode: string): string => {
  if (mode === '脚本') return 'blue'
  if (mode === '直控') return 'orange'
  return 'green'
}

/** 来源 → 展示词条 key（未知值按用户级兜底） */
export const sourceLabelKey = (mode: string): string => {
  if (mode === '脚本') return 'edit.configRestoreModeScript'
  if (mode === '直控') return 'edit.configRestoreModeDirect'
  return 'edit.configRestoreModeUser'
}

/** 是否跨配置来源恢复（两侧都已标注且不一致；未声明来源侧为 null 即不跨） */
export const isCrossSourceRestore = (
  backupMode: string | null | undefined,
  currentMode: string | null | undefined
): boolean => Boolean(backupMode && currentMode && backupMode !== currentMode)

/** 恢复确认弹窗内容：跨来源时换标题并追加来源切换说明（脚本级额外提醒共享配置被覆盖） */
export const buildRestoreConfirm = (
  t: (key: string, named?: Record<string, string>) => string,
  base: { title: string; desc: string },
  backupMode: string | null | undefined,
  currentMode: string | null | undefined
): { title: string; paragraphs: string[] } => {
  if (!isCrossSourceRestore(backupMode, currentMode)) {
    return { title: base.title, paragraphs: [base.desc] }
  }
  const paragraphs = [
    t('edit.configRestoreCrossSourceDesc', {
      backup: t(sourceLabelKey(backupMode as string)),
      current: t(sourceLabelKey(currentMode as string)),
    }),
  ]
  if (backupMode === '脚本') {
    paragraphs.push(t('edit.configRestoreCrossSourceShared'))
  }
  return { title: t('edit.configRestoreCrossSourceTitle'), paragraphs: [base.desc, ...paragraphs] }
}

/** 强制恢复确认弹窗的文案（标题/损坏位置/风险/按钮）：各恢复入口共用同一份说法 */
export const buildCorruptedForceConfirm = (
  t: (key: string, named?: Record<string, string>) => string,
  detail: string
): { title: string; detail: string; desc: string; okText: string } => ({
  title: t('edit.configRestoreCorruptedTitle'),
  detail,
  desc: t('edit.configRestoreCorruptedDesc'),
  okText: t('edit.configRestoreForceAction'),
})

/** 强制恢复确认弹窗内容：第一段红字标明损坏位置，第二段写风险（与文案同源，渲染也共用） */
export const corruptedForceConfirmContent = (detail: string, desc: string): VNode =>
  h('div', [
    h('p', { style: { color: 'var(--ant-color-error)', margin: '0 0 8px' } }, detail),
    h('p', { style: { margin: 0 } }, desc),
  ])
