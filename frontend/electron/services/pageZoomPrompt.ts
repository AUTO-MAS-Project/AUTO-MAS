import { app, dialog, type BrowserWindow } from 'electron'

const MIN_PAGE_ZOOM = 0.75
const DEFAULT_PAGE_ZOOM = 1

const messages = {
  zh: {
    message: '当前界面缩放低于 75%，要恢复到 100% 吗？',
    buttons: ['恢复到 100%', '保持当前缩放'],
  },
  en: {
    message: 'The interface zoom is below 75%. Restore it to 100%?',
    buttons: ['Restore to 100%', 'Keep current zoom'],
  },
  ja: {
    message: '画面の拡大率が 75% 未満です。100% に戻しますか？',
    buttons: ['100% に戻す', '現在の拡大率を維持'],
  },
}

export async function promptLowPageZoom(win: BrowserWindow, language: unknown): Promise<void> {
  const contents = win.webContents
  if (contents.getZoomFactor() >= MIN_PAGE_ZOOM) return

  const locale = (typeof language === 'string' && language ? language : app.getLocale())
    .toLowerCase()
    .split('-')[0]
  const copy = locale === 'zh' || locale === 'ja' ? messages[locale] : messages.en
  const { response } = await dialog.showMessageBox(win, {
    ...copy,
    type: 'question',
    title: 'AUTO-MAS',
    defaultId: 1,
    cancelId: 1,
  })
  if (response === 0 && !contents.isDestroyed()) contents.setZoomFactor(DEFAULT_PAGE_ZOOM)
}
